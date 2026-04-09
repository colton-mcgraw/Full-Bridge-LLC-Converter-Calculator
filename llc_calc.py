import csv
import io
import math
import os
import re
import sys
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, ttk


AWG_TABLE = [
    (30, 0.0509),
    (28, 0.0804),
    (26, 0.128),
    (24, 0.205),
    (22, 0.326),
    (20, 0.518),
    (18, 0.823),
    (16, 1.31),
    (14, 2.08),
    (12, 3.31),
    (10, 5.26),
    (8, 8.37),
]

# Coilcraft SER subset from public parametric search listings.
COILCRAFT_SER_CATALOG = [
    {"part": "SER8050-451", "l_uh": 0.45, "irms_a": 11.72, "isat_a": 31.12, "dcr_mohm": 3.5},
    {"part": "SER8050-501", "l_uh": 0.50, "irms_a": 13.52, "isat_a": 22.68, "dcr_mohm": 2.5},
    {"part": "SER8050-811", "l_uh": 0.80, "irms_a": 9.43, "isat_a": 25.20, "dcr_mohm": 5.88},
    {"part": "SER8050-112", "l_uh": 1.10, "irms_a": 11.97, "isat_a": 14.50, "dcr_mohm": 3.5},
    {"part": "SER8050-202", "l_uh": 2.00, "irms_a": 10.79, "isat_a": 9.78, "dcr_mohm": 5.88},
    {"part": "SER8052-122", "l_uh": 1.20, "irms_a": 8.11, "isat_a": 19.18, "dcr_mohm": 7.2},
    {"part": "SER8052-182", "l_uh": 1.80, "irms_a": 7.94, "isat_a": 14.88, "dcr_mohm": 9.5},
    {"part": "SER8052-242", "l_uh": 2.40, "irms_a": 7.58, "isat_a": 11.80, "dcr_mohm": 9.5},
    {"part": "SER8052-312", "l_uh": 3.10, "irms_a": 8.71, "isat_a": 8.00, "dcr_mohm": 7.2},
    {"part": "SER8052-332", "l_uh": 3.20, "irms_a": 6.25, "isat_a": 10.24, "dcr_mohm": 14.33},
    {"part": "SER8052-402", "l_uh": 4.00, "irms_a": 6.30, "isat_a": 8.24, "dcr_mohm": 14.33},
    {"part": "SER8052-452", "l_uh": 4.50, "irms_a": 7.68, "isat_a": 6.14, "dcr_mohm": 9.5},
    {"part": "SER8052-612", "l_uh": 6.10, "irms_a": 7.31, "isat_a": 4.58, "dcr_mohm": 9.5},
    {"part": "SER8052-802", "l_uh": 8.00, "irms_a": 6.31, "isat_a": 3.86, "dcr_mohm": 14.33},
    {"part": "SER8052-103", "l_uh": 10.0, "irms_a": 6.32, "isat_a": 3.10, "dcr_mohm": 14.33},
]

OUTPUT_TOOLTIPS = {
    "n_ratio": "Effective ratio used by equations. center-tap: n_eff = Np/(2*Ns_half); full-bridge secondary: n_eff = Np/Ns.",
    "r_load": "Effective DC load resistance at output. Lower value means heavier load.",
    "r_ac": "Approx reflected AC load seen by LLC tank. Drives tank Q and gain shape.",
    "fr_khz": "Series resonance of Lr and Cr. Peak gain region is around this frequency.",
    "fm_khz": "Resonance of (Lr + Lm) with Cr. Should stay below fr in normal LLC design.",
    "zr": "Characteristic tank impedance sqrt(Lr/Cr). Higher Zr reduces tank current.",
    "qe": "Effective loaded quality factor Qe = Zr/Rac (standard LLC convention). Lower Qe means heavier loading.",
    "ln": "Inductance ratio Lm/Lr. Higher Ln tends to reduce magnetizing current.",
    "fn": "Normalized frequency Fs/fr. Operating point of switching relative to resonance.",
    "m_required": "Required gain from tank and transformer for requested Vin to Vout.",
    "m_fha_est": "Approx gain from a simplified FHA model at current operating point.",
    "eff_est": "Estimated full-load efficiency from simplified conduction/switching losses.",
    "awg_p": "Primary wire gauge suggestion or override result.",
    "awg_s": "Secondary wire gauge suggestion or override result.",
    "lout_uh": "Estimated output filter inductor for center-tapped SR stage ripple target.",
    "cout_uf": "Estimated total output capacitance for requested ripple target.",
    "c_per_cap_uf": "Estimated per-cap value assuming the selected number of parallel caps.",
    "c_per_cap_rec_uf": "Nearest practical standard per-cap value at or above estimated requirement.",
    "f_rect_khz": "Ripple frequency used for output capacitor sizing. full-bridge secondary uses fr; center-tap uses 2fr.",
    "esr_max_total_mohm": "Maximum allowed total output-cap ESR (all caps in parallel) so ESR-induced ripple stays within budget.",
    "esr_max_per_cap_mohm": "Maximum allowed ESR per capacitor, considering the selected number of parallel caps.",
    "i_ripple_a": "Estimated inductor ripple current peak-to-peak.",
    "v_ripple_pp": "Estimated output voltage ripple peak-to-peak.",
    "coilcraft_lr": "Best Coilcraft SER candidate for resonant inductor target and current needs.",
    "coilcraft_lout": "Best Coilcraft SER candidate for output filter inductor target and current needs.",
    "ser_catalog_info": "Current source used for SER recommendations.",
    "cap_choice": "Recommended output capacitor part from loaded capacitor CSV.",
    "cap_check": "PASS/FAIL check vs required per-cap capacitance, ESR limit, and voltage rating margin.",
    "cap_catalog_info": "Current source used for output capacitor recommendations.",
}

OUTPUT_RECOMMENDED_RANGES = {
    "n_ratio": "rec: 1.5 to 14.0",
    "qe": "rec: 0.20 to 0.50",
    "ln": "rec: 2.5 to 10.0",
    "fn": "rec: 0.50 to 1.80",
    "m_required": "rec: 0.45 to 1.35",
}


class LLCQuickCalc:
    @staticmethod
    def _resource_path(name: str) -> str:
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, name)

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Full-Bridge LLC Quick Calculator")
        self.root.geometry("1040x860")
        self.root.minsize(920, 760)

        self.inputs = {
            "vin": tk.StringVar(value="400"),      # Input bus voltage [V]
            "vout": tk.StringVar(value="48"),      # Output voltage [V]
            "pout": tk.StringVar(value="1000"),    # Output power [W]
            "p_turns": tk.StringVar(value="80"),   # Primary turns Np
            "s_turns": tk.StringVar(value="10"),   # Secondary turns Ns
            "lr_uh": tk.StringVar(value="30"),     # Resonant inductor [uH]
            "cr_nf": tk.StringVar(value="100"),    # Resonant capacitor [nF]
            "lm_uh": tk.StringVar(value="180"),    # Magnetizing inductance [uH]
            "fs_khz": tk.StringVar(value="100"),   # Switching frequency [kHz]
            "il_ripple_pct": tk.StringVar(value="25"),  # Output inductor ripple [% of Iout]
            "v_ripple_pct": tk.StringVar(value="1.0"),  # Output voltage ripple [%]
            "caps_parallel": tk.StringVar(value="2"),   # Number of output capacitors in parallel
        }

        self.optimization_mode = tk.StringVar(value="balanced")
        self.secondary_topology = tk.StringVar(value="center-tap")
        self.link_turns_vout = tk.BooleanVar(value=True)
        self.use_output_inductor = tk.BooleanVar(value=False)
        self.cap_series_filter = tk.StringVar(value="")

        self.assumptions = {
            "bmax_t": tk.StringVar(value="0.22"),
            "core_area_mm2": tk.StringVar(value="120"),
            "rds_on_mohm": tk.StringVar(value="45"),
            "tr_tf_ns": tk.StringVar(value="75"),
            "j_primary": tk.StringVar(value="4.0"),
            "j_secondary": tk.StringVar(value="5.0"),
            "awg_p_override": tk.StringVar(value=""),
            "awg_s_override": tk.StringVar(value=""),
            "rth_mos": tk.StringVar(value="1.7"),
            "rth_xfmr": tk.StringVar(value="2.2"),
            "rth_rect": tk.StringVar(value="1.9"),
            "rth_tank": tk.StringVar(value="2.6"),
            "sr_rds_on_mohm": tk.StringVar(value="3.5"),  # Assumption for SR FET Rds(on)
        }

        self.outputs = {
            "n_ratio": tk.StringVar(value="-"),
            "r_load": tk.StringVar(value="-"),
            "r_ac": tk.StringVar(value="-"),
            "fr_khz": tk.StringVar(value="-"),
            "fm_khz": tk.StringVar(value="-"),
            "zr": tk.StringVar(value="-"),
            "qe": tk.StringVar(value="-"),
            "ln": tk.StringVar(value="-"),
            "fn": tk.StringVar(value="-"),
            "m_required": tk.StringVar(value="-"),
            "m_fha_est": tk.StringVar(value="-"),
            "eff_est": tk.StringVar(value="-"),
            "awg_p": tk.StringVar(value="-"),
            "awg_s": tk.StringVar(value="-"),
            "lout_uh": tk.StringVar(value="-"),
            "cout_uf": tk.StringVar(value="-"),
            "c_per_cap_uf": tk.StringVar(value="-"),
            "c_per_cap_rec_uf": tk.StringVar(value="-"),
            "f_rect_khz": tk.StringVar(value="-"),
            "esr_max_total_mohm": tk.StringVar(value="-"),
            "esr_max_per_cap_mohm": tk.StringVar(value="-"),
            "i_ripple_a": tk.StringVar(value="-"),
            "v_ripple_pp": tk.StringVar(value="-"),
            "coilcraft_lr": tk.StringVar(value="-"),
            "coilcraft_lout": tk.StringVar(value="-"),
            "ser_catalog_info": tk.StringVar(value="Built-in SER subset"),
            "cap_choice": tk.StringVar(value="No cap catalog loaded"),
            "cap_check": tk.StringVar(value="-"),
            "cap_catalog_info": tk.StringVar(value="No cap CSV loaded"),
        }

        self.ser_catalog = list(COILCRAFT_SER_CATALOG)
        self.cap_catalog = []
        self.output_value_labels = {}
        self._last_calc = None
        self.status_text = tk.StringVar(value="Edit any input value to update results.")
        self._redraw_job = None  # Storage for redraw state
        self._syncing_turns = False

        default_catalog = self._resource_path("Power Inductors.csv")
        if os.path.exists(default_catalog):
            try:
                count = self._load_ser_catalog_from_path(default_catalog)
                self.outputs["ser_catalog_info"].set(f"Loaded local CSV ({count} parts)")
            except Exception:
                # Keep built-in subset if local file cannot be parsed.
                pass

        self._build_ui()
        self._bind_updates()
        self.recalculate()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root)
        outer.pack(fill=tk.BOTH, expand=True)

        self.main_scroll_canvas = tk.Canvas(outer, highlightthickness=0)
        vscroll = ttk.Scrollbar(outer, orient="vertical", command=self.main_scroll_canvas.yview)
        self.main_scroll_canvas.configure(yscrollcommand=vscroll.set)

        self.main_scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        main = ttk.Frame(self.main_scroll_canvas, padding=14)
        self._main_canvas_window = self.main_scroll_canvas.create_window((0, 0), window=main, anchor="nw")

        main.bind("<Configure>", self._on_main_scroll_configure)
        self.main_scroll_canvas.bind("<Configure>", self._on_main_canvas_configure)
        self.main_scroll_canvas.bind_all("<MouseWheel>", self._on_main_mousewheel)

        ttk.Label(main, text="Full-Bridge LLC Quick Calculator", font=("Segoe UI", 15, "bold")).pack(anchor=tk.W)

        body = ttk.Frame(main)
        body.pack(fill=tk.BOTH, expand=False)

        left = ttk.LabelFrame(body, text="Inputs", padding=10)
        right = ttk.LabelFrame(body, text="Derived Outputs", padding=10)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        input_rows = [
            ("vin", "Vin [V]"),
            ("vout", "Vout [V]"),
            ("pout", "Pout [W]"),
            ("p_turns", "Primary Turns Np"),
            ("s_turns", "Secondary Turns Ns (per half, CT)"),
            ("lr_uh", "Lr [uH]"),
            ("cr_nf", "Cr [nF]"),
            ("lm_uh", "Lm [uH]"),
            ("fs_khz", "Fs [kHz]"),
            ("il_ripple_pct", "Output IL Ripple [% of Iout]"),
            ("v_ripple_pct", "Output V Ripple [%]"),
            ("caps_parallel", "Parallel Output Caps [count]"),
        ]

        for row, (key, label) in enumerate(input_rows):
            ttk.Label(left, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(left, textvariable=self.inputs[key], width=18).grid(
                row=row,
                column=1,
                sticky="ew",
                pady=3,
                padx=(8, 0),
            )

        ttk.Label(left, text="Cap Series Filter (optional)").grid(row=len(input_rows), column=0, sticky="w", pady=(10, 3))
        ttk.Entry(left, textvariable=self.cap_series_filter, width=18).grid(
            row=len(input_rows),
            column=1,
            sticky="ew",
            pady=(10, 3),
            padx=(8, 0),
        )

        button_row = len(input_rows) + 1
        ttk.Label(left, text="Optimization Mode").grid(row=button_row, column=0, sticky="w", pady=(10, 3))
        ttk.Combobox(
            left,
            textvariable=self.optimization_mode,
            values=["balanced", "maximize efficiency", "minimize size"],
            state="readonly",
            width=20,
        ).grid(row=button_row, column=1, sticky="ew", pady=(10, 3), padx=(8, 0))

        ttk.Label(left, text="Secondary Topology").grid(row=button_row + 1, column=0, sticky="w", pady=(3, 3))
        ttk.Combobox(
            left,
            textvariable=self.secondary_topology,
            values=["center-tap", "full-bridge"],
            state="readonly",
            width=20,
        ).grid(row=button_row + 1, column=1, sticky="ew", pady=(3, 3), padx=(8, 0))

        ttk.Checkbutton(
            left,
            text="Link Vout <-> Turns",
            variable=self.link_turns_vout,
        ).grid(row=button_row + 2, column=0, columnspan=2, sticky="w", pady=(3, 3))

        ttk.Checkbutton(
            left,
            text="Use Separate Output Lout",
            variable=self.use_output_inductor,
        ).grid(row=button_row + 3, column=0, columnspan=2, sticky="w", pady=(0, 3))

        ttk.Button(left, text="Best Guess Fill Blanks", command=self.best_guess_fill_blanks).grid(
            row=button_row + 4,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 3),
        )
        ttk.Button(left, text="Export CSV Snapshot", command=self.export_csv_snapshot).grid(
            row=button_row + 5,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=3,
        )
        ttk.Button(left, text="Load Coilcraft SER CSV", command=self.load_ser_catalog_csv).grid(
            row=button_row + 6,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=3,
        )

        ttk.Button(left, text="Load Output Caps CSV", command=self.load_output_caps_csv).grid(
            row=button_row + 7,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=3,
        )

        assumptions_frame = ttk.LabelFrame(left, text="Assumptions", padding=8)
        assumptions_frame.grid(row=button_row + 8, column=0, columnspan=2, sticky="ew", pady=(10, 3))

        assumption_rows = [
            ("bmax_t", "Bmax [T]"),
            ("core_area_mm2", "Core Area Ae [mm^2]"),
            ("rds_on_mohm", "MOSFET Rds(on) [mohm]"),
            ("tr_tf_ns", "MOSFET tr/tf [ns]"),
            ("sr_rds_on_mohm", "SR FET Rds(on) [mohm]"),
            ("j_primary", "Primary J [A/mm^2]"),
            ("j_secondary", "Secondary J [A/mm^2]"),
            ("awg_p_override", "Primary AWG (blank=auto)"),
            ("awg_s_override", "Secondary AWG (blank=auto)"),
            ("rth_mos", "Rth MOS [C/W]"),
            ("rth_xfmr", "Rth XFMR [C/W]"),
            ("rth_rect", "Rth Rect [C/W]"),
            ("rth_tank", "Rth Tank [C/W]"),
        ]
        for row, (key, label) in enumerate(assumption_rows):
            ttk.Label(assumptions_frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(assumptions_frame, textvariable=self.assumptions[key], width=12).grid(
                row=row,
                column=1,
                sticky="e",
                pady=2,
                padx=(8, 0),
            )
        assumptions_frame.columnconfigure(1, weight=1)

        left.columnconfigure(1, weight=1)

        output_rows = [
            ("n_ratio", "Effective Turns Ratio n_eff (used in model)"),
            ("r_load", "Load Resistance Rload [ohm]"),
            ("r_ac", "Reflected AC Load Rac [ohm]"),
            ("fr_khz", "Series Resonant Freq fr [kHz]"),
            ("fm_khz", "Magnetizing Resonant fm [kHz]"),
            ("zr", "Characteristic Impedance Zr [ohm]"),
            ("qe", "Effective Quality Factor Qe"),
            ("ln", "Inductance Ratio Ln = Lm/Lr"),
            ("fn", "Normalized Frequency fn = Fs/fr"),
            ("m_required", "Required DC Gain Mreq = n*Vout/Vin"),
            ("m_fha_est", "Approx FHA Gain @ fn"),
            ("eff_est", "Estimated Efficiency @ Full Load [%]"),
            ("awg_p", "Primary Wire Best AWG"),
            ("awg_s", "Secondary Wire Best AWG"),
            ("lout_uh", "Output Filter Lout [uH]"),
            ("cout_uf", "Output Filter Cout Total [uF]"),
            ("c_per_cap_uf", "Per-Cap Value [uF]"),
            ("c_per_cap_rec_uf", "Recommended Std Per-Cap [uF]"),
            ("f_rect_khz", "Cap Sizing Ripple Freq [kHz]"),
            ("esr_max_total_mohm", "Max Total ESR [mohm]"),
            ("esr_max_per_cap_mohm", "Max ESR Per Cap [mohm]"),
            ("i_ripple_a", "Inductor Ripple dIL [A]"),
            ("v_ripple_pp", "Output Ripple dVpp [V]"),
            ("coilcraft_lr", "Coilcraft SER Suggestion for Lr"),
            ("coilcraft_lout", "Coilcraft SER Suggestion for Lout"),
            ("ser_catalog_info", "SER Catalog Source"),
            ("cap_choice", "Output Cap Recommendation"),
            ("cap_check", "Output Cap Check"),
            ("cap_catalog_info", "Cap Catalog Source"),
        ]

        for row, (key, label) in enumerate(output_rows):
            name_label = ttk.Label(right, text=label)
            name_label.grid(row=row, column=0, sticky="w", pady=3)
            value_label = tk.Label(right, textvariable=self.outputs[key], font=("Consolas", 10, "bold"), fg="#111111")
            value_label.grid(
                row=row,
                column=1,
                sticky="e",
                pady=3,
                padx=(8, 0),
            )
            self.output_value_labels[key] = value_label
            tip = OUTPUT_TOOLTIPS.get(key, "")
            self._attach_tooltip(name_label, tip)
            self._attach_tooltip(value_label, tip)

            recommended_text = OUTPUT_RECOMMENDED_RANGES.get(key, "")
            if recommended_text:
                ttk.Label(right, text=recommended_text, foreground="#666666").grid(
                    row=row,
                    column=2,
                    sticky="w",
                    pady=3,
                    padx=(8, 0),
                )

        right.columnconfigure(1, weight=1)

        xf_frame = ttk.LabelFrame(right, text="Power Stage Schematic (Simplified)", padding=6)
        xf_frame.grid(row=len(output_rows), column=0, columnspan=2, sticky="ew", pady=(10, 2))
        self.xfmr_canvas = tk.Canvas(xf_frame, height=190, background="#f8f8f8", highlightthickness=1)
        self.xfmr_canvas.pack(fill=tk.X, expand=True)
        ttk.Label(
            xf_frame,
            text="Overview: H-bridge -> Lr/Cr tank -> transformer -> rectification -> Lout/Cout/load.",
            foreground="#444",
        ).pack(anchor="w", pady=(4, 0))

        chart_row = ttk.Frame(main)
        chart_row.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        gain_frame = ttk.LabelFrame(chart_row, text="Approx FHA Gain vs Normalized Frequency", padding=8)
        gain_frame.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=(0, 6))
        thermal_frame = ttk.LabelFrame(chart_row, text="Thermal Rise + Efficiency vs Output Power", padding=8)
        thermal_frame.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=(6, 0))

        self.plot_canvas = tk.Canvas(gain_frame, height=240, background="white", highlightthickness=1)
        self.plot_canvas.pack(fill=tk.BOTH, expand=True)
        self.thermal_canvas = tk.Canvas(thermal_frame, height=240, background="white", highlightthickness=1)
        self.thermal_canvas.pack(fill=tk.BOTH, expand=True)
        self.xfmr_canvas.bind("<Configure>", self._on_chart_resize)
        self.plot_canvas.bind("<Configure>", self._on_chart_resize)
        self.thermal_canvas.bind("<Configure>", self._on_chart_resize)

        stage_frame = ttk.LabelFrame(main, text="Idealized Stage Voltage Profile", padding=8)
        stage_frame.pack(fill=tk.BOTH, expand=False, pady=(10, 0))
        self.stage_canvas = tk.Canvas(stage_frame, height=200, background="white", highlightthickness=1)
        self.stage_canvas.pack(fill=tk.BOTH, expand=True)
        self.stage_canvas.bind("<Configure>", self._on_chart_resize)

        feas_frame = ttk.LabelFrame(main, text="Why Invalid? (Feasibility Checks)", padding=8)
        feas_frame.pack(fill=tk.BOTH, expand=False, pady=(10, 0))
        self.feasibility_text = tk.Text(feas_frame, height=6, wrap="word")
        self.feasibility_text.pack(fill=tk.BOTH, expand=True)
        self.feasibility_text.tag_configure("ok", foreground="#2e7d32")
        self.feasibility_text.tag_configure("warn", foreground="#b26a00")
        self.feasibility_text.tag_configure("error", foreground="#c62828")
        self.feasibility_text.configure(state="disabled")

        ttk.Label(main, textvariable=self.status_text, foreground="#333").pack(fill=tk.X, pady=(12, 0))

    def _set_feasibility_text(self, lines: list[str]) -> None:
        self.feasibility_text.configure(state="normal")
        self.feasibility_text.delete("1.0", tk.END)
        if not lines:
            self.feasibility_text.insert(tk.END, "No feasibility rule violations detected.", "ok")
        else:
            for idx, line in enumerate(lines):
                tag = None
                if line.startswith("ERROR:"):
                    tag = "error"
                elif line.startswith("WARN:"):
                    tag = "warn"
                self.feasibility_text.insert(tk.END, line, tag)
                if idx < len(lines) - 1:
                    self.feasibility_text.insert(tk.END, "\n")
        self.feasibility_text.configure(state="disabled")

    def _attach_tooltip(self, widget, text: str) -> None:
        if not text:
            return

        def show(_event):
            if hasattr(widget, "_tip_window") and widget._tip_window is not None:
                return
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            x = widget.winfo_rootx() + 14
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            tip.wm_geometry(f"+{x}+{y}")
            tk.Label(
                tip,
                text=text,
                justify="left",
                background="#fff8dc",
                relief="solid",
                borderwidth=1,
                padx=6,
                pady=3,
                wraplength=420,
                fg="#222",
            ).pack()
            widget._tip_window = tip

        def hide(_event):
            tip = getattr(widget, "_tip_window", None)
            if tip is not None:
                tip.destroy()
                widget._tip_window = None

        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", hide, add="+")
        widget.bind("<ButtonPress>", hide, add="+")

    def _set_output_highlights(self, invalid_keys: list[str]) -> None:
        for key, label in self.output_value_labels.items():
            if key in invalid_keys:
                label.configure(fg="#c62828")
            else:
                label.configure(fg="#111111")

    def _on_main_scroll_configure(self, _event=None) -> None:
        if hasattr(self, "main_scroll_canvas"):
            self.main_scroll_canvas.configure(scrollregion=self.main_scroll_canvas.bbox("all"))

    def _on_main_canvas_configure(self, event) -> None:
        if hasattr(self, "main_scroll_canvas") and hasattr(self, "_main_canvas_window"):
            self.main_scroll_canvas.itemconfigure(self._main_canvas_window, width=event.width)

    def _on_main_mousewheel(self, event) -> None:
        if not hasattr(self, "main_scroll_canvas"):
            return
        if event.delta == 0:
            return
        units = int(-event.delta / 120)
        if units != 0:
            self.main_scroll_canvas.yview_scroll(units, "units")

    def _draw_transformer_view(self, p_turns: float, s_turns: float) -> None:
        c = self.xfmr_canvas
        c.delete("all")
        c.update_idletasks()
        w = max(420, c.winfo_width())
        h = max(180, c.winfo_height())
        compact = w < 760

        left = 16
        right = w - 16
        span = max(360, right - left)
        scale = max(0.75, min(1.35, span / 660.0))

        top = 26
        bot = h - 28
        mid = int((top + bot) * 0.5)

        def sx(frac: float) -> float:
            return left + frac * span

        x_bridge_l = sx(0.00)
        x_bridge_r = sx(0.16)
        x_tank_l = sx(0.19)
        x_tank_r = sx(0.36)
        x_tx = sx(0.47)
        x_rect = sx(0.61)
        x_out = sx(0.76)

        head_font = ("Segoe UI", 7 if compact else 8, "bold")
        label_font = ("Segoe UI", 8 if compact else 9, "bold")
        small_font = ("Segoe UI", 7 if compact else 8)

        stage_names = [
            "Bridge",
            "Tank",
            "Xfmr" if compact else "Transformer",
            "Rect",
            "Output",
        ]
        c.create_text((x_bridge_l + x_bridge_r) * 0.5, 10, text=stage_names[0], fill="#1b5eaa", font=head_font)
        c.create_text((x_tank_l + x_tank_r) * 0.5, 10, text=stage_names[1], fill="#8c4b00", font=head_font)
        c.create_text(x_tx, 10, text=stage_names[2], fill="#2e7d32", font=head_font)
        c.create_text(x_rect, 10, text=stage_names[3], fill="#7b1fa2", font=head_font)
        c.create_text(x_out + (28 * scale), 10, text=stage_names[4], fill="#444", font=head_font)

        c.create_line(x_bridge_l, top, x_bridge_r, top, fill="#555", width=2)
        c.create_line(x_bridge_l, bot, x_bridge_r, bot, fill="#555", width=2)
        c.create_text(x_bridge_l + 2, top - 10, text="+Vin", anchor="w", fill="#444", font=label_font)
        c.create_text(x_bridge_l + 2, bot + 11, text="-Vin", anchor="w", fill="#444", font=label_font)

        sw_w = max(12, int(18 * scale))
        sw_h = max(14, int(22 * scale))
        sx1 = x_bridge_l + (22 * scale)
        sx2 = x_bridge_l + (66 * scale)
        c.create_rectangle(sx1, top + 10, sx1 + sw_w, top + 10 + sw_h, outline="#1976d2", width=2)
        c.create_rectangle(sx2, top + 10, sx2 + sw_w, top + 10 + sw_h, outline="#1976d2", width=2)
        c.create_rectangle(sx1, bot - 10 - sw_h, sx1 + sw_w, bot - 10, outline="#1976d2", width=2)
        c.create_rectangle(sx2, bot - 10 - sw_h, sx2 + sw_w, bot - 10, outline="#1976d2", width=2)

        x_mid_leg = sx1 + sw_w
        c.create_line(x_mid_leg, top + 10 + sw_h, x_mid_leg, bot - 10 - sw_h, fill="#1976d2", width=2)
        c.create_line(x_mid_leg, mid, x_tank_l - 8, mid, fill="#1976d2", width=2)
        if not compact:
            c.create_text((x_bridge_l + x_bridge_r) * 0.5, bot + 14, text="Full-Bridge Drive", fill="#1976d2", font=small_font)

        x_lr = x_tank_l
        c.create_line(x_tank_l - 8, mid, x_lr, mid, fill="#333", width=2)
        lr_step = max(8, int(12 * scale))
        for i in range(4):
            x0 = x_lr + i * lr_step
            c.create_arc(x0, mid - 9, x0 + lr_step, mid + 9, start=0, extent=180, style="arc", width=2, outline="#ef6c00")
        x_after_lr = x_lr + (4 * lr_step)
        c.create_text(x_lr + (2 * lr_step), mid - 18, text="Lr", fill="#ef6c00", font=label_font)

        x_cr = x_after_lr + (18 * scale)
        c.create_line(x_after_lr, mid, x_cr - 8, mid, fill="#333", width=2)
        c.create_line(x_cr, mid - 14, x_cr, mid + 14, fill="#7b1fa2", width=2)
        c.create_line(x_cr + 9, mid - 14, x_cr + 9, mid + 14, fill="#7b1fa2", width=2)
        c.create_line(x_cr + 9, mid, x_tank_r, mid, fill="#333", width=2)
        c.create_text(x_cr + 4, mid - 22, text="Cr", fill="#7b1fa2", font=label_font)

        c.create_line(x_tank_r, mid, x_tx - (38 * scale), mid, fill="#333", width=2)
        c.create_line(x_tx - (12 * scale), top - 2, x_tx - (12 * scale), bot + 2, fill="#444", width=2)
        c.create_line(x_tx + (8 * scale), top - 2, x_tx + (8 * scale), bot + 2, fill="#444", width=2)

        for i in range(5):
            y0 = mid - 34 + i * 13
            c.create_arc(x_tx - (40 * scale), y0, x_tx - (18 * scale), y0 + 11, start=90, extent=180, style="arc", width=2, outline="#1976d2")
        c.create_text(x_tx - (58 * scale), mid, text=f"Np={int(round(p_turns))}", fill="#1976d2", anchor="e", font=label_font)

        topo = self.secondary_topology.get().strip().lower()
        if topo == "center-tap":
            for i in range(3):
                y0 = top + 12 + i * 11
                c.create_arc(x_tx + (14 * scale), y0, x_tx + (36 * scale), y0 + 10, start=270, extent=180, style="arc", width=2, outline="#2e7d32")
            for i in range(3):
                y0 = bot - 12 - i * 11
                c.create_arc(x_tx + (14 * scale), y0 - 10, x_tx + (36 * scale), y0, start=270, extent=180, style="arc", width=2, outline="#2e7d32")

            if compact:
                c.create_text(x_tx + (44 * scale), mid, text=f"Ns={int(round(s_turns))}/half", fill="#2e7d32", anchor="w", font=small_font)
            else:
                c.create_text(x_tx + (44 * scale), top + 20, text=f"Ns1={int(round(s_turns))}", fill="#2e7d32", anchor="w", font=small_font)
                c.create_text(x_tx + (44 * scale), bot - 20, text=f"Ns2={int(round(s_turns))}", fill="#2e7d32", anchor="w", font=small_font)

            c.create_line(x_tx + (36 * scale), mid, x_rect - (24 * scale), mid, fill="#2e7d32", width=2)
            c.create_text(x_rect - (28 * scale), mid - 8, text="CT", fill="#2e7d32", anchor="e", font=small_font)

            d1y = top + 26
            d2y = bot - 26
            c.create_line(x_tx + (36 * scale), d1y, x_rect - 10, d1y, fill="#2e7d32", width=2)
            c.create_line(x_tx + (36 * scale), d2y, x_rect - 10, d2y, fill="#2e7d32", width=2)
            c.create_polygon(x_rect - 10, d1y - 7, x_rect + 2, d1y, x_rect - 10, d1y + 7, outline="#7b1fa2", fill="", width=2)
            c.create_line(x_rect + 2, d1y - 8, x_rect + 2, d1y + 8, fill="#7b1fa2", width=2)
            c.create_polygon(x_rect - 10, d2y - 7, x_rect + 2, d2y, x_rect - 10, d2y + 7, outline="#7b1fa2", fill="", width=2)
            c.create_line(x_rect + 2, d2y - 8, x_rect + 2, d2y + 8, fill="#7b1fa2", width=2)
            c.create_line(x_rect + 2, d1y, x_rect + 16, d1y, fill="#333", width=2)
            c.create_line(x_rect + 2, d2y, x_rect + 16, d2y, fill="#333", width=2)
            c.create_line(x_rect + 16, d1y, x_rect + 16, d2y, fill="#333", width=2)
            c.create_text(x_rect + 18, top + 20, text="SR", anchor="w", fill="#7b1fa2", font=small_font)
            x_sec_out = x_rect + 16
        else:
            for i in range(5):
                y0 = mid - 34 + i * 13
                c.create_arc(x_tx + (14 * scale), y0, x_tx + (36 * scale), y0 + 11, start=270, extent=180, style="arc", width=2, outline="#2e7d32")
            c.create_text(x_tx + (44 * scale), mid, text=f"Ns={int(round(s_turns))}", fill="#2e7d32", anchor="w", font=label_font)

            rect_l = x_rect - 6
            rect_r = x_rect + max(24, int(30 * scale))
            c.create_line(x_tx + (36 * scale), mid - 12, rect_l, mid - 12, fill="#2e7d32", width=2)
            c.create_line(x_tx + (36 * scale), mid + 12, rect_l, mid + 12, fill="#2e7d32", width=2)
            c.create_rectangle(rect_l, mid - 24, rect_r, mid + 24, outline="#7b1fa2", width=2)
            c.create_text((rect_l + rect_r) * 0.5, mid, text="BR", fill="#7b1fa2", font=small_font)
            x_sec_out = rect_r

        use_output_inductor = self.use_output_inductor.get()
        x_lout_l = x_out
        lout_step = max(10, int(14 * scale))
        if use_output_inductor:
            x_lout_r = x_lout_l + (3 * lout_step)
            c.create_line(x_sec_out, mid, x_lout_l, mid, fill="#333", width=2)
            for i in range(3):
                x0 = x_lout_l + i * lout_step
                c.create_arc(x0, mid - 9, x0 + lout_step, mid + 9, start=0, extent=180, style="arc", width=2, outline="#ef6c00")
            c.create_text((x_lout_l + x_lout_r) * 0.5, mid - 18, text="Lout", fill="#ef6c00", font=label_font)
        else:
            x_lout_r = x_lout_l + max(18, int(26 * scale))
            c.create_line(x_sec_out, mid, x_lout_r, mid, fill="#333", width=2)
            c.create_text((x_lout_l + x_lout_r) * 0.5, mid - 18, text="No Lout", fill="#666", font=small_font)

        x_vout = x_lout_r + max(12, int(16 * scale))
        c.create_line(x_lout_r, mid, x_vout, mid, fill="#333", width=2)
        c.create_line(x_vout, mid, x_vout, bot, fill="#333", width=2)
        c.create_line(x_bridge_l, bot, right, bot, fill="#555", width=2)

        x_cap = x_vout + max(12, int(18 * scale))
        c.create_line(x_vout, mid, x_cap, mid, fill="#333", width=2)
        c.create_line(x_cap, mid - 13, x_cap, mid + 13, fill="#6a1b9a", width=2)
        c.create_line(x_cap + 8, mid - 13, x_cap + 8, mid + 13, fill="#6a1b9a", width=2)
        c.create_line(x_cap + 8, mid, x_cap + 8, bot, fill="#333", width=2)
        c.create_text(x_cap + 4, mid - 22, text="Cout", fill="#6a1b9a", font=label_font)

        x_load_l = x_cap + max(20, int(30 * scale))
        x_load_r = x_load_l + max(14, int(18 * scale))
        c.create_line(x_vout, mid, x_load_l, mid, fill="#333", width=2)
        c.create_rectangle(x_load_l, mid - 13, x_load_r, mid + 13, outline="#444", width=2)
        c.create_line(x_load_r, mid, x_load_r, bot, fill="#333", width=2)
        c.create_text(x_load_l + ((x_load_r - x_load_l) * 0.5), mid - 22, text="Load", fill="#444", font=label_font)

        topo_label = "CT secondary" if topo == "center-tap" else "Full-bridge secondary"
        c.create_text(x_tx + (52 * scale), bot + 14, text=topo_label, fill="#2e7d32", font=small_font)
        c.create_text(x_vout + 3, bot + 14, text="Vout", anchor="w", fill="#444", font=label_font)

    def _bind_updates(self) -> None:
        for key, var in self.inputs.items():
            var.trace_add("write", lambda *_args, input_key=key: self._on_input_change(input_key))
        for var in self.assumptions.values():
            var.trace_add("write", lambda *_args: self._on_input_change(None))
        self.optimization_mode.trace_add("write", lambda *_args: self._on_input_change(None))
        self.secondary_topology.trace_add("write", lambda *_args: self._on_input_change(None))
        self.use_output_inductor.trace_add("write", lambda *_args: self._on_input_change(None))
        self.cap_series_filter.trace_add("write", lambda *_args: self._on_input_change(None))

    def _sync_turns_and_vout(self, changed_key: str) -> None:
        if not self.link_turns_vout.get():
            return

        if self._syncing_turns:
            return

        if changed_key not in {"vout", "p_turns", "s_turns"}:
            return

        try:
            vin = self._optional_float("vin")
            vout = self._optional_float("vout")
            p_turns = self._optional_float("p_turns")
            s_turns = self._optional_float("s_turns")

            if vin is None or vin <= 0:
                return

            self._syncing_turns = True
            sec_scale = self._secondary_scale()

            if changed_key == "vout":
                if vout is None or vout <= 0:
                    return
                if p_turns is not None and p_turns > 0:
                    new_s = max(1, int(round(p_turns * vout / (vin * sec_scale))))
                    if self.inputs["s_turns"].get().strip() != str(new_s):
                        self.inputs["s_turns"].set(str(new_s))
                elif s_turns is not None and s_turns > 0:
                    new_p = max(1, int(round(s_turns * vin * sec_scale / vout)))
                    if self.inputs["p_turns"].get().strip() != str(new_p):
                        self.inputs["p_turns"].set(str(new_p))

            elif changed_key == "p_turns":
                if p_turns is None or p_turns <= 0:
                    return
                if s_turns is not None and s_turns > 0:
                    new_vout = vin * sec_scale * s_turns / p_turns
                    self.inputs["vout"].set(f"{new_vout:.6g}")
                elif vout is not None and vout > 0:
                    new_s = max(1, int(round(p_turns * vout / (vin * sec_scale))))
                    self.inputs["s_turns"].set(str(new_s))

            elif changed_key == "s_turns":
                if s_turns is None or s_turns <= 0:
                    return
                if p_turns is not None and p_turns > 0:
                    new_vout = vin * sec_scale * s_turns / p_turns
                    self.inputs["vout"].set(f"{new_vout:.6g}")
                elif vout is not None and vout > 0:
                    new_p = max(1, int(round(s_turns * vin * sec_scale / vout)))
                    self.inputs["p_turns"].set(str(new_p))
        finally:
            self._syncing_turns = False

    def _on_input_change(self, changed_key=None) -> None:
        if isinstance(changed_key, str):
            self._sync_turns_and_vout(changed_key)
        self.recalculate()

    def _on_chart_resize(self, _event=None) -> None:
        if self._redraw_job is not None:
            self.root.after_cancel(self._redraw_job)
        self._redraw_job = self.root.after(120, self._redraw_charts)

    def _redraw_charts(self) -> None:
        self._redraw_job = None
        if not self._last_calc:
            return
        self._draw_transformer_view(
            self._last_calc["p_turns"],
            self._last_calc["s_turns"],
        )
        self._draw_stage_voltage_plot(self._last_calc["stage_profile"])
        self._draw_gain_plot(
            self._last_calc["qe"],
            self._last_calc["ln"],
            self._last_calc["m_required"],
            self._last_calc["fn"],
        )
        self._draw_thermal_plot(
            self._last_calc["vin"],
            self._last_calc["vout"],
            self._last_calc["pout"],
            self._last_calc["p_turns"],
            self._last_calc["s_turns"],
            self._last_calc["fs_khz"],
            self._last_calc["lr_uh"],
            self._last_calc["cr_nf"],
            self._last_calc["lm_uh"],
            self._last_calc["assumptions"],
        )

    def _optional_float(self, key: str):
        text = self.inputs[key].get().strip()
        if text == "":
            return None
        return float(text)

    def _set_if_blank(self, key: str, value: float, digits: int = 6) -> bool:
        if self.inputs[key].get().strip() != "":
            return False
        self.inputs[key].set(f"{value:.{digits}g}")
        return True

    def _get_assumptions(self) -> dict:
        result = {}
        optional_awg_keys = {"awg_p_override", "awg_s_override"}
        for key, var in self.assumptions.items():
            text = var.get().strip()
            if key in optional_awg_keys:
                if text == "":
                    result[key] = None
                    continue
                result[key] = float(text)
                if result[key] <= 0:
                    raise ValueError(f"Assumption {key} must be > 0")
                continue
            if text == "":
                raise ValueError(f"Assumption {key} is blank")
            result[key] = float(text)
            if result[key] <= 0:
                raise ValueError(f"Assumption {key} must be > 0")
        return result

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    def _secondary_scale(self, topology: str | None = None) -> float:
        mode = topology if topology is not None else self.secondary_topology.get().strip().lower()
        return 2.0 if mode == "center-tap" else 1.0

    def _effective_n(self, p_turns: float, s_turns: float, topology: str | None = None) -> float:
        return p_turns / (self._secondary_scale(topology) * s_turns)

    def _evaluate_feasibility(
        self,
        n: float,
        qe: float,
        ln: float,
        fn: float,
        m_required: float,
        fr_khz: float,
        fm_khz: float,
        fs_khz: float,
        il_ripple_pct: float,
        v_ripple_pct: float,
        caps_parallel: float,
    ) -> dict:
        warnings = []
        errors = []
        invalid_keys = []
        report_lines = []

        if m_required < 0.45 or m_required > 1.35:
            errors.append(f"Mreq={m_required:.3f} is outside practical FBLLC range [0.45, 1.35]")
            invalid_keys.append("m_required")

        if qe < 0.05 or qe > 2.0:
            errors.append(f"Qe={qe:.3f} is outside plausible FBLLC range [0.05, 2.0]")
            invalid_keys.append("qe")

        if fm_khz >= fr_khz:
            errors.append(f"fm={fm_khz:.3f} kHz must be less than fr={fr_khz:.3f} kHz")
            invalid_keys.extend(["fm_khz", "fr_khz"])

        if fs_khz < 50 or fs_khz > 250:
            warnings.append(f"Fs={fs_khz:.2f} kHz is outside common practical range [50, 250] kHz")

        if fr_khz < 40 or fr_khz > 300:
            warnings.append(f"fr={fr_khz:.2f} kHz is outside common practical range [40, 300] kHz")

        if il_ripple_pct < 10 or il_ripple_pct > 50:
            warnings.append(f"Output inductor ripple target {il_ripple_pct:.2f}% is outside common range [10, 50]%")

        if v_ripple_pct < 0.1 or v_ripple_pct > 5.0:
            warnings.append(f"Output ripple target {v_ripple_pct:.2f}% is outside common range [0.1, 5.0]%")

        if caps_parallel < 1 or caps_parallel > 12:
            warnings.append(f"Parallel cap count {caps_parallel:.2f} is unusual (typical 1 to 12)")

        n_clamped = self._clamp(n, 1.5, 14.0)
        if abs(n_clamped - n) > 1e-9:
            warnings.append(f"Turns ratio clamped to practical range: {n:.3f} -> {n_clamped:.3f}")
            invalid_keys.append("n_ratio")

        qe_clamped = self._clamp(qe, 0.2, 0.5)
        if abs(qe_clamped - qe) > 1e-9:
            warnings.append(f"Qe out of practical range and clamped for plotting/model use: {qe:.3f} -> {qe_clamped:.3f}")
            invalid_keys.append("qe")

        ln_clamped = self._clamp(ln, 2.5, 10.0)
        if abs(ln_clamped - ln) > 1e-9:
            warnings.append(f"Ln clamped for practical FBLLC tank range: {ln:.3f} -> {ln_clamped:.3f}")
            invalid_keys.append("ln")

        fn_clamped = self._clamp(fn, 0.5, 1.8)
        if abs(fn_clamped - fn) > 1e-9:
            warnings.append(f"fn clamped for practical operation window: {fn:.3f} -> {fn_clamped:.3f}")
            invalid_keys.append("fn")

        for msg in errors:
            report_lines.append(f"ERROR: {msg}")
        for msg in warnings:
            report_lines.append(f"WARN: {msg}")

        return {
            "n_clamped": n_clamped,
            "qe_clamped": qe_clamped,
            "ln_clamped": ln_clamped,
            "fn_clamped": fn_clamped,
            "warnings": warnings,
            "errors": errors,
            "invalid_keys": list(dict.fromkeys(invalid_keys)),
            "report_lines": report_lines,
        }

    @staticmethod
    def _compute_output_filter(
        vout: float,
        i_out: float,
        rect_ripple_hz: float,
        il_ripple_pct: float,
        v_ripple_pct: float,
        caps_parallel: float,
        use_output_inductor: bool,
    ) -> dict:
        f_ripple = max(1.0, rect_ripple_hz)
        delta_v = max(0.001 * vout, (v_ripple_pct / 100.0) * vout)

        if use_output_inductor:
            delta_i = max(0.02 * i_out, (il_ripple_pct / 100.0) * i_out)
            # Equivalent rectified source headroom assumption for center-tapped SR output stage.
            v_headroom = max(0.04 * vout, 1.5)
            l_out = (v_headroom * 0.5) / (delta_i * f_ripple)
            c_out = delta_i / (8.0 * f_ripple * delta_v)
        else:
            # Capacitor-input filter approximation (no separate output inductor).
            l_out = 0.0
            delta_i = i_out
            c_out = i_out / max(1e-9, f_ripple * delta_v)

        caps_count = max(1.0, round(caps_parallel))
        return {
            "lout_uh": l_out * 1e6,
            "cout_uf": c_out * 1e6,
            "c_per_cap_uf": (c_out * 1e6) / caps_count,
            "i_ripple_a": delta_i,
            "v_ripple_pp": delta_v,
            "f_rect_khz": f_ripple / 1e3,
        }

    @staticmethod
    def _recommend_standard_cap_uf(target_uf: float) -> float:
        target = max(1e-6, target_uf)
        e12 = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2]
        decade = 10.0 ** math.floor(math.log10(target))

        for scale in [0.1, 1.0, 10.0, 100.0]:
            base = decade * scale
            for val in e12:
                cand = val * base
                if cand >= target:
                    return cand

        return target

    @staticmethod
    def _estimate_esr_limits_mohm(v_ripple_pp: float, ripple_current_pp: float, caps_parallel: float) -> tuple[float, float]:
        # Conservative split: allocate half of ripple budget to ESR term.
        v_esr_budget_pp = 0.5 * max(1e-9, v_ripple_pp)
        i_pp = max(1e-9, ripple_current_pp)
        esr_total_ohm = v_esr_budget_pp / i_pp
        n_caps = max(1.0, round(caps_parallel))
        esr_per_cap_ohm = esr_total_ohm * n_caps
        return esr_total_ohm * 1e3, esr_per_cap_ohm * 1e3

    def _recommend_output_cap(
        self,
        per_cap_target_uf: float,
        esr_max_per_cap_mohm: float,
        vout: float,
    ) -> tuple[str, str]:
        if not self.cap_catalog:
            return "No cap catalog loaded", "Load cap CSV to evaluate PASS/FAIL"

        series_filter = self.cap_series_filter.get().strip().lower()
        candidates = [part for part in self.cap_catalog if (not series_filter or series_filter in part["part"].lower())]
        if not candidates:
            return "No cap match for series filter", "FAIL: no candidates"

        best = None
        best_score = None
        for part in candidates:
            c_ok = part["c_uf"] >= per_cap_target_uf
            esr_ok = part["esr_mohm"] <= esr_max_per_cap_mohm
            vr = part.get("vr_v")
            v_ok = True if vr is None else (vr >= 1.25 * vout)

            c_deficit = max(0.0, (per_cap_target_uf - part["c_uf"]) / max(1e-6, per_cap_target_uf))
            esr_excess = max(0.0, (part["esr_mohm"] - esr_max_per_cap_mohm) / max(1e-6, esr_max_per_cap_mohm))
            score = (35.0 * c_deficit) + (35.0 * esr_excess)
            score += 0.5 * abs(math.log(max(1e-6, part["c_uf"]) / max(1e-6, per_cap_target_uf)))
            score += 0.01 * part["esr_mohm"]
            if not v_ok:
                score += 20.0

            if best is None or score < best_score:
                best = (part, c_ok, esr_ok, v_ok)
                best_score = score

        part, c_ok, esr_ok, v_ok = best
        vr_text = "n/a" if part.get("vr_v") is None else f"{part['vr_v']:.3g}V"
        choice = f"{part['part']} (C={part['c_uf']:.3g}uF, ESR={part['esr_mohm']:.3g}mohm, Vr={vr_text})"

        checks = []
        checks.append("C ok" if c_ok else "C low")
        checks.append("ESR ok" if esr_ok else "ESR high")
        checks.append("Vr ok" if v_ok else "Vr low")
        status = "PASS" if (c_ok and esr_ok and v_ok) else "FAIL"
        check = f"{status}: " + ", ".join(checks)
        return choice, check

    def _build_stage_profile(self, vin: float, vout: float, n_eff: float, filt: dict, use_output_inductor: bool) -> list[dict]:
        sec_vpk = vin / max(1e-6, n_eff)
        out_ripple_pp = max(1e-6, filt["v_ripple_pp"])

        if use_output_inductor:
            # Idealized pre-cap node ripple shown larger than final output ripple for visual comparison.
            post_lout_ripple_pp = max(0.02 * vout, 8.0 * out_ripple_pp)
            post_lout_label = "After Lout"
            post_lout_desc = f"Approx ripple dVpp~{post_lout_ripple_pp:.3g}V"
        else:
            post_lout_ripple_pp = max(0.03 * vout, 10.0 * out_ripple_pp)
            post_lout_label = "Rectified Node"
            post_lout_desc = f"No Lout, node ripple~{post_lout_ripple_pp:.3g}V"

        return [
            {
                "label": "PFC DC In",
                "value": vin,
                "ripple_pp": 0.0,
                "desc": f"Vdc={vin:.3g}V",
            },
            {
                "label": "Bridge PWM",
                "value": vin,
                "ripple_pp": 0.0,
                "desc": f"Square: +/-{vin:.3g}V (Vpp={2.0 * vin:.3g}V)",
            },
            {
                "label": "Secondary AC",
                "value": sec_vpk,
                "ripple_pp": 0.0,
                "desc": f"Ideal sec pk~{sec_vpk:.3g}V",
            },
            {
                "label": post_lout_label,
                "value": vout,
                "ripple_pp": post_lout_ripple_pp,
                "desc": post_lout_desc,
            },
            {
                "label": "After Cout",
                "value": vout,
                "ripple_pp": out_ripple_pp,
                "desc": f"Output ripple dVpp~{out_ripple_pp:.3g}V",
            },
        ]

    def _draw_stage_voltage_plot(self, stage_profile: list[dict]) -> None:
        c = self.stage_canvas
        c.delete("all")
        c.update_idletasks()
        w = max(420, c.winfo_width())
        h = max(180, c.winfo_height())

        if not stage_profile:
            return

        compact = w < 760
        pad_l = 48
        pad_r = 22
        pad_t = 24
        pad_b = 46 if compact else 56
        usable_w = max(220, w - pad_l - pad_r)
        usable_h = max(90, h - pad_t - pad_b)

        vmax = 0.0
        for item in stage_profile:
            vmax = max(vmax, item["value"] + 0.5 * item["ripple_pp"])
        vmax = max(1.0, vmax * 1.12)

        def sx(idx: int) -> float:
            count = max(1, len(stage_profile) - 1)
            return pad_l + (idx * usable_w / count)

        def sy(v: float) -> float:
            return pad_t + (usable_h - (v * usable_h / vmax))

        c.create_rectangle(pad_l, pad_t, w - pad_r, h - pad_b, outline="#a0a0a0")

        for tick in [0.0, 0.25, 0.5, 0.75, 1.0]:
            v = tick * vmax
            y = sy(v)
            c.create_line(pad_l - 5, y, pad_l, y, fill="#666")
            c.create_text(pad_l - 8, y, text=f"{v:.0f}", anchor="e", fill="#444", font=("Segoe UI", 8))

        c.create_text(16, pad_t + (usable_h * 0.5), text="Voltage [V]", angle=90, fill="#303030", font=("Segoe UI", 9))

        line_pts = []
        for i, item in enumerate(stage_profile):
            x = sx(i)
            y = sy(item["value"])
            line_pts.extend([x, y])
        c.create_line(*line_pts, fill="#1565c0", width=2, smooth=True)

        for i, item in enumerate(stage_profile):
            x = sx(i)
            y = sy(item["value"])
            c.create_oval(x - 4, y - 4, x + 4, y + 4, fill="#1565c0", outline="#1565c0")

            ripple_pp = item["ripple_pp"]
            if ripple_pp > 0:
                y_hi = sy(item["value"] + 0.5 * ripple_pp)
                y_lo = sy(max(0.0, item["value"] - 0.5 * ripple_pp))
                c.create_line(x, y_hi, x, y_lo, fill="#ef6c00", width=2)
                c.create_line(x - 5, y_hi, x + 5, y_hi, fill="#ef6c00", width=2)
                c.create_line(x - 5, y_lo, x + 5, y_lo, fill="#ef6c00", width=2)
                c.create_text(x, y_hi - 8, text=f"dVpp {ripple_pp:.3g}V", fill="#ef6c00", font=("Segoe UI", 7), anchor="s")

            c.create_text(x, h - pad_b + 14, text=item["label"], fill="#333", font=("Segoe UI", 8, "bold"), angle=18 if compact else 0)
            if not compact:
                c.create_text(x, h - 14, text=item["desc"], fill="#555", font=("Segoe UI", 7))

        if compact:
            c.create_text(
                pad_l,
                h - 12,
                text="Idealized stage voltages with ripple whiskers at post-Lout and post-Cout",
                anchor="w",
                fill="#555",
                font=("Segoe UI", 7),
            )

    def _recommend_coilcraft_ser(self, target_l_uh: float, irms_req_a: float, isat_req_a: float) -> str:
        candidates = []
        for part in self.ser_catalog:
            if part["irms_a"] < irms_req_a or part["isat_a"] < isat_req_a:
                continue

            l_err = abs(math.log(max(1e-6, target_l_uh) / max(1e-6, part["l_uh"])))
            current_margin = (part["irms_a"] - irms_req_a) + 0.4 * (part["isat_a"] - isat_req_a)
            score = (5.0 * l_err) - (0.04 * current_margin) + (0.01 * part["dcr_mohm"])
            candidates.append((score, part))

        if not candidates:
            return "No SER match in local catalog subset"

        candidates.sort(key=lambda x: x[0])
        best = candidates[0][1]
        return (
            f"{best['part']} (L={best['l_uh']}uH, Irms={best['irms_a']}A, "
            f"Isat={best['isat_a']}A, DCR={best['dcr_mohm']}mohm)"
        )

    @staticmethod
    def _gain_fha(fn: float, qe: float, ln: float) -> float:
        num = 1.0 + (1.0 / ln) - (1.0 / (ln * fn * fn))
        den = (fn - (1.0 / fn)) / max(1e-6, qe)
        return 1.0 / math.sqrt((num * num) + (den * den))

    @staticmethod
    def _pick_awg(required_area_mm2: float) -> tuple[int, float]:
        for awg, area in AWG_TABLE:
            if area >= required_area_mm2:
                return awg, area
        return AWG_TABLE[-1]

    @staticmethod
    def _area_for_awg(awg_value: float) -> tuple[int, float]:
        awg_list = [awg for awg, _ in AWG_TABLE]
        nearest = min(awg_list, key=lambda x: abs(x - awg_value))
        for awg, area in AWG_TABLE:
            if awg == nearest:
                return awg, area
        return AWG_TABLE[-1]

    @staticmethod
    def _estimate_turns(vin: float, fs_khz: float, n_target: float, b_max: float, core_area_mm2: float) -> tuple[int, int, float]:
        a_e = core_area_mm2 * 1e-6
        fs = fs_khz * 1e3
        np_min = vin / (4.0 * b_max * a_e * fs)
        p_turns = max(3, math.ceil(np_min * 1.15))
        s_turns = max(1, round(p_turns / max(0.6, n_target)))
        n_actual = p_turns / s_turns
        return p_turns, s_turns, n_actual

    def _estimate_losses(
        self,
        vin: float,
        vout: float,
        pout: float,
        p_turns: float,
        s_turns: float,
        fs_khz: float,
        lr_uh: float,
        cr_nf: float,
        lm_uh: float,
        assumptions: dict,
    ) -> dict:
        fs_hz = fs_khz * 1e3

        i_out = pout / vout
        i_pri = pout / (0.95 * vin)
        i_res = 1.8 * i_pri

        j_primary = assumptions["j_primary"]
        j_secondary = assumptions["j_secondary"]
        awg_p_override = assumptions["awg_p_override"]
        awg_s_override = assumptions["awg_s_override"]

        if awg_p_override is None:
            awg_p, area_p = self._pick_awg(i_pri / j_primary)
        else:
            awg_p, area_p = self._area_for_awg(awg_p_override)

        if awg_s_override is None:
            awg_s, area_s = self._pick_awg(i_out / j_secondary)
        else:
            awg_s, area_s = self._area_for_awg(awg_s_override)

        rds_ohm = assumptions["rds_on_mohm"] * 1e-3
        sr_rds_ohm = assumptions["sr_rds_on_mohm"] * 1e-3
        tr_tf_s = assumptions["tr_tf_ns"] * 1e-9

        p_mos_cond = 4.0 * (i_pri * i_pri) * rds_ohm * 0.55
        p_mos_sw = 4.0 * 0.5 * vin * i_pri * tr_tf_s * fs_hz
        p_rect = 2.0 * (i_out * i_out) * sr_rds_ohm * 0.5

        winding_scale = (p_turns + s_turns) / 100.0
        p_xfmr_cu = 0.9 * (i_pri * i_pri) * winding_scale / max(0.08, area_p)
        p_xfmr_cu += 0.55 * (i_out * i_out) * winding_scale / max(0.08, area_s)
        p_xfmr_core = 1.4 * (fs_khz / 100.0) ** 1.35

        p_tank = (i_res * i_res) * (0.018 + 0.008 * math.sqrt(max(0.4, fs_khz / 100.0)))
        p_cap = (i_res * i_res) * 0.01
        p_misc = 0.006 * pout + 0.7

        total_loss = p_mos_cond + p_mos_sw + p_rect + p_xfmr_cu + p_xfmr_core + p_tank + p_cap + p_misc
        eta = pout / (pout + total_loss)

        copper_proxy = (p_turns * area_p) + (s_turns * area_s)
        magnetics_proxy = copper_proxy + 0.03 * (lr_uh + lm_uh) + 0.002 * cr_nf

        return {
            "efficiency": eta,
            "total_loss": total_loss,
            "awg_p": awg_p,
            "awg_s": awg_s,
            "magnetics_proxy": magnetics_proxy,
            "mos_cond": p_mos_cond,
            "mos_sw": p_mos_sw,
            "rect": p_rect,
            "xfmr_cu": p_xfmr_cu,
            "xfmr_core": p_xfmr_core,
            "tank": p_tank,
            "cap": p_cap,
        }

    def _find_best_design(self, vin: float, vout: float, pout: float, assumptions: dict, mode: str) -> dict:
        sec_scale = self._secondary_scale()
        n_eff_center = max(1.0, min(8.0, 0.92 * vin / vout))
        n_center = sec_scale * n_eff_center
        best = None

        if mode == "maximize efficiency":
            w_loss, w_size, w_gain = 1.35, 0.03, 18.0
        elif mode == "minimize size":
            w_loss, w_size, w_gain = 0.85, 0.16, 18.0
        else:
            w_loss, w_size, w_gain = 1.0, 0.07, 16.0

        for fs_khz in range(70, 181, 5):
            for n_target in [n_center * f for f in [0.8, 0.9, 1.0, 1.1, 1.2]]:
                if n_target < 1.8 or n_target > 16.0:
                    continue

                p_turns, s_turns, n_actual = self._estimate_turns(
                    vin,
                    float(fs_khz),
                    n_target,
                    assumptions["bmax_t"],
                    assumptions["core_area_mm2"],
                )
                n_eff = n_actual / sec_scale
                r_load = (vout * vout) / pout
                r_ac = (8.0 / (math.pi * math.pi)) * (n_eff * n_eff) * r_load

                for qe_target in [0.25, 0.35, 0.5, 0.7, 1.0]:
                    zr = max(5.0, qe_target * r_ac)
                    fr_hz = (fs_khz * 1e3) / 1.05
                    omega = 2.0 * math.pi * fr_hz
                    lr_uh = (zr / omega) * 1e6
                    cr_nf = (1.0 / (zr * omega)) * 1e9

                    for ln_target in [4.5, 6.0, 7.5]:
                        lm_uh = ln_target * lr_uh

                        losses = self._estimate_losses(
                            vin,
                            vout,
                            pout,
                            float(p_turns),
                            float(s_turns),
                            float(fs_khz),
                            lr_uh,
                            cr_nf,
                            lm_uh,
                            assumptions,
                        )

                        m_required = (n_eff * vout) / vin
                        if m_required < 0.45 or m_required > 1.35:
                            continue
                        gain_penalty = abs(m_required - 0.95)
                        score = (w_loss * losses["total_loss"]) + (w_size * losses["magnetics_proxy"])
                        score += w_gain * gain_penalty

                        candidate = {
                            "score": score,
                            "fs_khz": float(fs_khz),
                            "p_turns": float(p_turns),
                            "s_turns": float(s_turns),
                            "lr_uh": lr_uh,
                            "cr_nf": cr_nf,
                            "lm_uh": lm_uh,
                            "efficiency": losses["efficiency"],
                        }
                        if best is None or candidate["score"] < best["score"]:
                            best = candidate

        if best is None:
            raise ValueError("No feasible best-guess design found")
        return best

    def best_guess_fill_blanks(self) -> None:
        try:
            vin = self._optional_float("vin")
            vout = self._optional_float("vout")
            pout = self._optional_float("pout")
            assumptions = self._get_assumptions()
            mode = self.optimization_mode.get().strip().lower()

            if vin is None or vout is None or pout is None:
                raise ValueError("Provide Vin, Vout, and Pout for best guess")
            if vin <= 0 or vout <= 0 or pout <= 0:
                raise ValueError("Vin, Vout, and Pout must be > 0")

            design = self._find_best_design(float(vin), float(vout), float(pout), assumptions, mode)
            self._set_if_blank("fs_khz", design["fs_khz"], digits=6)
            self._set_if_blank("p_turns", design["p_turns"], digits=8)
            self._set_if_blank("s_turns", design["s_turns"], digits=8)
            self._set_if_blank("lr_uh", design["lr_uh"], digits=7)
            self._set_if_blank("cr_nf", design["cr_nf"], digits=7)
            self._set_if_blank("lm_uh", design["lm_uh"], digits=7)
            self._set_if_blank("il_ripple_pct", 25.0, digits=6)
            self._set_if_blank("v_ripple_pct", 1.0, digits=6)
            self._set_if_blank("caps_parallel", 2.0, digits=6)

            self.recalculate()
            self.status_text.set(
                f"Best guess ({mode}) applied to blank fields, est eff {design['efficiency'] * 100.0:.2f}%."
            )
        except Exception as ex:
            self.status_text.set(f"Best guess failed: {ex}")

    def export_csv_snapshot(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Export LLC Snapshot",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="llc_snapshot.csv",
        )
        if not path:
            self.status_text.set("CSV export canceled.")
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", datetime.now().isoformat(timespec="seconds")])
                writer.writerow([])
                writer.writerow(["section", "name", "value"])
                writer.writerow(["setting", "optimization_mode", self.optimization_mode.get().strip()])
                for key, var in self.inputs.items():
                    writer.writerow(["input", key, var.get().strip()])
                for key, var in self.assumptions.items():
                    writer.writerow(["assumption", key, var.get().strip()])
                for key, var in self.outputs.items():
                    writer.writerow(["output", key, var.get().strip()])
            self.status_text.set(f"CSV exported: {path}")
        except Exception as ex:
            self.status_text.set(f"CSV export failed: {ex}")

    @staticmethod
    def _to_float_maybe(text: str):
        cleaned = text.strip().lower()
        cleaned = cleaned.replace(",", "")
        cleaned = cleaned.replace("$", "")
        cleaned = cleaned.replace("uh", "").replace("µh", "")
        cleaned = cleaned.replace("mohm", "").replace("mω", "")
        cleaned = cleaned.replace("a", "")
        cleaned = re.sub(r"[^0-9eE+\-.]", "", cleaned)
        if cleaned == "" or cleaned == "-":
            return None
        return float(cleaned)

    @staticmethod
    def _normalize_header(text: str) -> str:
        lowered = text.lower().strip()
        return re.sub(r"[^a-z0-9]", "", lowered)

    @staticmethod
    def _find_header(headers: list[str], aliases: list[list[str]]):
        normalized_map = {LLCQuickCalc._normalize_header(h): h for h in headers}
        for alias_parts in aliases:
            for nkey, original in normalized_map.items():
                if all(part in nkey for part in alias_parts):
                    return original
        return None

    def load_ser_catalog_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Load Coilcraft SER Catalog CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            self.status_text.set("SER catalog load canceled.")
            return

        try:
            count = self._load_ser_catalog_from_path(path)
            self.outputs["ser_catalog_info"].set(f"Loaded CSV ({count} parts)")
            self.status_text.set(f"Loaded Coilcraft SER catalog: {count} parts")
            self.recalculate()
        except Exception as ex:
            self.status_text.set(f"SER catalog load failed: {ex}")

    def load_output_caps_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Load Output Capacitor CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            self.status_text.set("Output capacitor catalog load canceled.")
            return

        try:
            count = self._load_output_caps_catalog_from_path(path)
            self.outputs["cap_catalog_info"].set(f"Loaded CSV ({count} caps)")
            self.status_text.set(f"Loaded output capacitor catalog: {count} parts")
            self.recalculate()
        except Exception as ex:
            self.status_text.set(f"Output capacitor catalog load failed: {ex}")

    def _load_ser_catalog_from_path(self, path: str) -> int:
        imported = []
        with open(path, "rb") as f:
            raw = f.read()

        decoded = None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                decoded = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if decoded is None:
            raise ValueError("Unable to decode CSV file")

        reader = csv.DictReader(io.StringIO(decoded))
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")

        headers = list(reader.fieldnames)
        part_h = self._find_header(headers, [["part"], ["part", "number"], ["pn"]])
        l_h = self._find_header(headers, [["induct"], ["l"]])
        irms_h = self._find_header(headers, [["irms"], ["ir"], ["current", "rms"]])
        isat_h = self._find_header(headers, [["isat"], ["is", "at"], ["saturation", "current"]])
        dcr_h = self._find_header(headers, [["dcr"], ["dc", "res"], ["resistance"]])

        if not part_h or not l_h or not irms_h or not isat_h or not dcr_h:
            raise ValueError("CSV must include columns for part, inductance, Irms, Isat, and DCR")

        for row in reader:
            part = (row.get(part_h) or "").strip()
            if not part or "SER" not in part.upper():
                continue

            l_uh = self._to_float_maybe(row.get(l_h, ""))
            irms = self._to_float_maybe(row.get(irms_h, ""))
            isat = self._to_float_maybe(row.get(isat_h, ""))
            dcr = self._to_float_maybe(row.get(dcr_h, ""))
            if l_uh is None or irms is None or isat is None or dcr is None:
                continue

            imported.append(
                {
                    "part": part,
                    "l_uh": float(l_uh),
                    "irms_a": float(irms),
                    "isat_a": float(isat),
                    "dcr_mohm": float(dcr),
                }
            )

        if not imported:
            raise ValueError("No SER rows could be parsed from CSV")

        self.ser_catalog = imported
        return len(imported)

    def _load_output_caps_catalog_from_path(self, path: str) -> int:
        imported = []
        with open(path, "rb") as f:
            raw = f.read()

        decoded = None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                decoded = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if decoded is None:
            raise ValueError("Unable to decode CSV file")

        reader = csv.DictReader(io.StringIO(decoded))
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")

        headers = list(reader.fieldnames)
        part_h = self._find_header(headers, [["part"], ["part", "number"], ["pn"]])
        c_h = self._find_header(headers, [["capacit"], ["uf"], ["u", "f"]])
        esr_h = self._find_header(headers, [["esr"], ["res"], ["impedance"]])
        vr_h = self._find_header(headers, [["volt"], ["wv"], ["rating"]])

        if not part_h or not c_h or not esr_h:
            raise ValueError("CSV must include columns for part, capacitance, and ESR")

        for row in reader:
            part = (row.get(part_h) or "").strip()
            if not part:
                continue

            c_uf = self._to_float_maybe(row.get(c_h, ""))
            esr_mohm = self._to_float_maybe(row.get(esr_h, ""))
            vr_v = self._to_float_maybe(row.get(vr_h, "")) if vr_h else None
            if c_uf is None or esr_mohm is None:
                continue
            if c_uf <= 0 or esr_mohm <= 0:
                continue

            imported.append(
                {
                    "part": part,
                    "c_uf": float(c_uf),
                    "esr_mohm": float(esr_mohm),
                    "vr_v": float(vr_v) if vr_v is not None else None,
                }
            )

        if not imported:
            raise ValueError("No capacitor rows could be parsed from CSV")

        self.cap_catalog = imported
        return len(imported)

    def _draw_gain_plot(self, qe: float, ln: float, m_required: float, fn_current: float) -> None:
        c = self.plot_canvas
        c.delete("all")

        c.update_idletasks()
        w = max(360, c.winfo_width())
        h = max(180, c.winfo_height())
        pad = 36

        fn_min = 0.5
        fn_max = 2.0
        points = []
        max_gain = max(1.2, m_required * 1.35)
        for i in range(160):
            fn = fn_min + (fn_max - fn_min) * i / 159.0
            gain = self._gain_fha(fn, qe, ln)
            points.append((fn, gain))
            if gain > max_gain:
                max_gain = gain

        def sx(fn_val: float) -> float:
            return pad + (fn_val - fn_min) * (w - 2 * pad) / (fn_max - fn_min)

        def sy(gain_val: float) -> float:
            return h - pad - (gain_val * (h - 2 * pad) / max_gain)

        c.create_rectangle(pad, pad, w - pad, h - pad, outline="#a0a0a0")

        for tick in [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]:
            x = sx(tick)
            c.create_line(x, h - pad, x, h - pad + 6, fill="#606060")
            c.create_text(x, h - pad + 16, text=f"{tick:g}", fill="#404040", font=("Segoe UI", 8))

        for tick in [0.25, 0.5, 0.75, 1.0]:
            y_val = tick * max_gain
            y = sy(y_val)
            c.create_line(pad - 6, y, pad, y, fill="#606060")
            c.create_text(pad - 10, y, text=f"{y_val:.2f}", fill="#404040", font=("Segoe UI", 8), anchor="e")

        c.create_text(w / 2.0, h - 8, text="Normalized Frequency fn", fill="#303030", font=("Segoe UI", 9))
        c.create_text(16, h / 2.0, text="Gain", fill="#303030", font=("Segoe UI", 9), angle=90)

        line_points = []
        for fn, gain in points:
            line_points.extend([sx(fn), sy(gain)])
        c.create_line(*line_points, fill="#1769aa", width=2, smooth=True)

        y_req = sy(m_required)
        c.create_line(pad, y_req, w - pad, y_req, fill="#f57c00", dash=(4, 3), width=2)
        c.create_text(w - pad - 4, y_req - 8, text="Mreq", fill="#f57c00", font=("Segoe UI", 8), anchor="e")

        x_cur = sx(max(fn_min, min(fn_max, fn_current)))
        c.create_line(x_cur, pad, x_cur, h - pad, fill="#2e7d32", dash=(4, 3), width=2)
        c.create_text(x_cur + 4, pad + 10, text="fn", fill="#2e7d32", font=("Segoe UI", 8), anchor="w")

    def _draw_thermal_plot(
        self,
        vin: float,
        vout: float,
        pout_full: float,
        p_turns: float,
        s_turns: float,
        fs_khz: float,
        lr_uh: float,
        cr_nf: float,
        lm_uh: float,
        assumptions: dict,
    ) -> None:
        c = self.thermal_canvas
        c.delete("all")

        c.update_idletasks()
        w = max(360, c.winfo_width())
        h = max(180, c.winfo_height())
        pad = 36

        rth = {
            "MOSFETs": assumptions["rth_mos"],
            "Transformer": assumptions["rth_xfmr"],
            "Rectifier": assumptions["rth_rect"],
            "Tank": assumptions["rth_tank"],
        }

        traces = {
            "MOSFETs": [],
            "Transformer": [],
            "Rectifier": [],
            "Tank": [],
        }

        eff_trace = []
        for i in range(10):
            frac = (i + 1) / 10.0
            pout = pout_full * frac
            losses = self._estimate_losses(
                vin,
                vout,
                pout,
                p_turns,
                s_turns,
                fs_khz,
                lr_uh,
                cr_nf,
                lm_uh,
                assumptions,
            )

            p_mos = losses["mos_cond"] + losses["mos_sw"]
            p_xfmr = losses["xfmr_cu"] + losses["xfmr_core"]
            p_rect = losses["rect"]
            p_tank = losses["tank"] + losses["cap"]

            traces["MOSFETs"].append((frac, p_mos * rth["MOSFETs"]))
            traces["Transformer"].append((frac, p_xfmr * rth["Transformer"]))
            traces["Rectifier"].append((frac, p_rect * rth["Rectifier"]))
            traces["Tank"].append((frac, p_tank * rth["Tank"]))
            eff_trace.append((frac, losses["efficiency"] * 100.0))

        max_rise = max(20.0, max(val for line in traces.values() for _, val in line) * 1.15)
        min_eff = min(v for _, v in eff_trace)
        max_eff = max(v for _, v in eff_trace)
        eff_low = min(75.0, min_eff - 1.0)
        eff_high = max(99.0, max_eff + 0.6)

        def sx(frac: float) -> float:
            return pad + frac * (w - 2 * pad)

        def sy(rise_c: float) -> float:
            return h - pad - rise_c * (h - 2 * pad) / max_rise

        def sy_eff(eff_pct: float) -> float:
            return h - pad - (eff_pct - eff_low) * (h - 2 * pad) / max(1.0, eff_high - eff_low)

        c.create_rectangle(pad, pad, w - pad, h - pad, outline="#a0a0a0")

        for tick in [0.2, 0.4, 0.6, 0.8, 1.0]:
            x = sx(tick)
            c.create_line(x, h - pad, x, h - pad + 6, fill="#606060")
            c.create_text(x, h - pad + 16, text=f"{int(tick * 100)}%", fill="#404040", font=("Segoe UI", 8))

        for tick in [0.25, 0.5, 0.75, 1.0]:
            y_val = tick * max_rise
            y = sy(y_val)
            c.create_line(pad - 6, y, pad, y, fill="#606060")
            c.create_text(pad - 9, y, text=f"{y_val:.0f}", fill="#404040", font=("Segoe UI", 8), anchor="e")

        c.create_text(w / 2.0, h - 8, text="Output Power Fraction", fill="#303030", font=("Segoe UI", 9))
        c.create_text(16, h / 2.0, text="Temperature Rise [C]", fill="#303030", font=("Segoe UI", 9), angle=90)
        c.create_text(w - 14, h / 2.0, text="Efficiency [%]", fill="#303030", font=("Segoe UI", 9), angle=270)

        colors = {
            "MOSFETs": "#1976d2",
            "Transformer": "#ef6c00",
            "Rectifier": "#2e7d32",
            "Tank": "#6a1b9a",
        }

        legend_x = pad + 6
        legend_y = pad + 8
        for idx, name in enumerate(["MOSFETs", "Transformer", "Rectifier", "Tank"]):
            pts = []
            for frac, rise in traces[name]:
                pts.extend([sx(frac), sy(rise)])
            c.create_line(*pts, fill=colors[name], width=2, smooth=True)
            y_line = legend_y + idx * 15
            c.create_line(legend_x, y_line, legend_x + 16, y_line, fill=colors[name], width=2)
            c.create_text(legend_x + 20, y_line, text=name, anchor="w", fill="#303030", font=("Segoe UI", 8))

        for tick in [0.0, 0.25, 0.5, 0.75, 1.0]:
            eff_val = eff_low + tick * (eff_high - eff_low)
            y = sy_eff(eff_val)
            c.create_line(w - pad, y, w - pad + 6, y, fill="#424242")
            c.create_text(w - pad + 8, y, text=f"{eff_val:.1f}", fill="#424242", anchor="w", font=("Segoe UI", 8))

        eff_points = []
        for frac, eff_pct in eff_trace:
            eff_points.extend([sx(frac), sy_eff(eff_pct)])
        c.create_line(*eff_points, fill="#111111", width=2, dash=(5, 3), smooth=True)
        c.create_text(w - pad - 4, sy_eff(eff_trace[-1][1]) - 10, text="Eff", fill="#111111", anchor="e", font=("Segoe UI", 8))

    def recalculate(self) -> None:
        try:
            vin = self._optional_float("vin")
            vout = self._optional_float("vout")
            pout = self._optional_float("pout")
            p_turns = self._optional_float("p_turns")
            s_turns = self._optional_float("s_turns")
            lr_uh = self._optional_float("lr_uh")
            cr_nf = self._optional_float("cr_nf")
            lm_uh = self._optional_float("lm_uh")
            fs_khz = self._optional_float("fs_khz")
            il_ripple_pct = self._optional_float("il_ripple_pct")
            v_ripple_pct = self._optional_float("v_ripple_pct")
            caps_parallel = self._optional_float("caps_parallel")
            assumptions = self._get_assumptions()

            required = {
                "Vin": vin,
                "Vout": vout,
                "Pout": pout,
                "Pturns": p_turns,
                "Sturns": s_turns,
                "Lr": lr_uh,
                "Cr": cr_nf,
                "Lm": lm_uh,
                "Fs": fs_khz,
                "IL ripple %": il_ripple_pct,
                "V ripple %": v_ripple_pct,
                "Caps parallel": caps_parallel,
            }
            missing = [name for name, val in required.items() if val is None]
            if missing:
                raise ValueError("Missing input(s): " + ", ".join(missing))

            vin = float(vin)
            vout = float(vout)
            pout = float(pout)
            p_turns = float(p_turns)
            s_turns = float(s_turns)
            lr_uh = float(lr_uh)
            cr_nf = float(cr_nf)
            lm_uh = float(lm_uh)
            fs_khz = float(fs_khz)
            il_ripple_pct = float(il_ripple_pct)
            v_ripple_pct = float(v_ripple_pct)
            caps_parallel = float(caps_parallel)

            lr = lr_uh * 1e-6
            cr = cr_nf * 1e-9
            lm = lm_uh * 1e-6
            fs = fs_khz * 1e3
            n_eff = self._effective_n(p_turns, s_turns)

            for value, name in [
                (vin, "Vin"),
                (vout, "Vout"),
                (pout, "Pout"),
                (p_turns, "Pturns"),
                (s_turns, "Sturns"),
                (lr, "Lr"),
                (cr, "Cr"),
                (lm, "Lm"),
                (fs, "Fs"),
                (n_eff, "n_eff"),
                (il_ripple_pct, "IL ripple %"),
                (v_ripple_pct, "V ripple %"),
                (caps_parallel, "Caps parallel"),
            ]:
                if value <= 0:
                    raise ValueError(f"{name} must be > 0")

            r_load = (vout * vout) / pout
            r_ac = ((8.0 * n_eff / (math.pi * math.pi)) * r_load) # n_eff is doesn't need to be squared here because it's already accounted for in the effective turns ratio calculation
            fr = 1.0 / (2.0 * math.pi * math.sqrt(lr * cr))
            fm = 1.0 / (2.0 * math.pi * math.sqrt((lr + lm) * cr))
            zr = math.sqrt(lr / cr)
            qe = zr / r_ac
            ln = lm / lr
            fn = fs / fr
            m_required = (n_eff * vout) / vin

            feasibility = self._evaluate_feasibility(
                n_eff,
                qe,
                ln,
                fn,
                m_required,
                fr / 1e3,
                fm / 1e3,
                fs_khz,
                il_ripple_pct,
                v_ripple_pct,
                caps_parallel,
            )
            self._set_feasibility_text(feasibility["report_lines"])

            m_fha_est = self._gain_fha(feasibility["fn_clamped"], feasibility["qe_clamped"], feasibility["ln_clamped"])
            losses = self._estimate_losses(
                vin,
                vout,
                pout,
                p_turns,
                s_turns,
                fs_khz,
                lr_uh,
                cr_nf,
                lm_uh,
                assumptions,
            )
            use_output_inductor = self.use_output_inductor.get()
            rect_ripple_hz = fr * self._secondary_scale()
            filt = self._compute_output_filter(
                vout,
                pout / vout,
                rect_ripple_hz,
                il_ripple_pct,
                v_ripple_pct,
                caps_parallel,
                use_output_inductor,
            )
            stage_profile = self._build_stage_profile(vin, vout, n_eff, filt, use_output_inductor)
            c_per_cap_rec = self._recommend_standard_cap_uf(filt["c_per_cap_uf"])
            esr_total_mohm, esr_per_cap_mohm = self._estimate_esr_limits_mohm(
                filt["v_ripple_pp"],
                filt["i_ripple_a"],
                caps_parallel,
            )
            cap_choice, cap_check = self._recommend_output_cap(
                filt["c_per_cap_uf"],
                esr_per_cap_mohm,
                vout,
            )

            i_in_rms = pout / max(1e-6, vin)
            i_lr_rms_req = i_in_rms
            i_lr_sat_req = 1.8 * i_in_rms
            lr_part = self._recommend_coilcraft_ser(lr_uh, i_lr_rms_req, i_lr_sat_req)

            if use_output_inductor:
                i_out = pout / max(1e-6, vout)
                i_lout_rms_req = i_out
                i_lout_sat_req = i_out + (0.5 * filt["i_ripple_a"])
                lout_part = self._recommend_coilcraft_ser(filt["lout_uh"], i_lout_rms_req, i_lout_sat_req)
            else:
                lout_part = "Not used (Lout disabled)"

            self.outputs["n_ratio"].set(self._fmt(n_eff))
            self.outputs["r_load"].set(self._fmt(r_load))
            self.outputs["r_ac"].set(self._fmt(r_ac))
            self.outputs["fr_khz"].set(self._fmt(fr / 1e3))
            self.outputs["fm_khz"].set(self._fmt(fm / 1e3))
            self.outputs["zr"].set(self._fmt(zr))
            self.outputs["qe"].set(self._fmt(qe))
            self.outputs["ln"].set(self._fmt(ln))
            self.outputs["fn"].set(self._fmt(fn))
            self.outputs["m_required"].set(self._fmt(m_required))
            self.outputs["m_fha_est"].set(self._fmt(m_fha_est))
            self.outputs["eff_est"].set(self._fmt(losses["efficiency"] * 100.0))
            self.outputs["awg_p"].set(str(losses["awg_p"]))
            self.outputs["awg_s"].set(str(losses["awg_s"]))
            self.outputs["lout_uh"].set(self._fmt(filt["lout_uh"]))
            self.outputs["cout_uf"].set(self._fmt(filt["cout_uf"]))
            self.outputs["c_per_cap_uf"].set(self._fmt(filt["c_per_cap_uf"]))
            self.outputs["c_per_cap_rec_uf"].set(self._fmt(c_per_cap_rec))
            self.outputs["f_rect_khz"].set(self._fmt(filt["f_rect_khz"]))
            self.outputs["esr_max_total_mohm"].set(self._fmt(esr_total_mohm))
            self.outputs["esr_max_per_cap_mohm"].set(self._fmt(esr_per_cap_mohm))
            self.outputs["i_ripple_a"].set(self._fmt(filt["i_ripple_a"]))
            self.outputs["v_ripple_pp"].set(self._fmt(filt["v_ripple_pp"]))
            self.outputs["coilcraft_lr"].set(lr_part)
            self.outputs["coilcraft_lout"].set(lout_part)
            self.outputs["cap_choice"].set(cap_choice)
            self.outputs["cap_check"].set(cap_check)
            self._set_output_highlights(feasibility["invalid_keys"])
            self._draw_transformer_view(p_turns, s_turns)
            self._draw_stage_voltage_plot(stage_profile)

            self._last_calc = {
                "qe": feasibility["qe_clamped"],
                "ln": feasibility["ln_clamped"],
                "m_required": m_required,
                "fn": feasibility["fn_clamped"],
                "vin": vin,
                "vout": vout,
                "pout": pout,
                "p_turns": p_turns,
                "s_turns": s_turns,
                "fs_khz": fs_khz,
                "lr_uh": lr_uh,
                "cr_nf": cr_nf,
                "lm_uh": lm_uh,
                "assumptions": assumptions,
                "stage_profile": stage_profile,
            }
            self._draw_gain_plot(feasibility["qe_clamped"], feasibility["ln_clamped"], m_required, feasibility["fn_clamped"])
            self._draw_thermal_plot(vin, vout, pout, p_turns, s_turns, fs_khz, lr_uh, cr_nf, lm_uh, assumptions)

            if feasibility["errors"]:
                self.status_text.set("Computed with invalid values: " + " | ".join(feasibility["errors"][:2]))
            elif feasibility["warnings"]:
                self.status_text.set("OK with warnings: " + " | ".join(feasibility["warnings"][:2]))
            else:
                self.status_text.set("OK: values updated")
        except Exception as ex:
            for key in self.outputs:
                self.outputs[key].set("-")
            self._last_calc = None
            if hasattr(self, "plot_canvas"):
                self.plot_canvas.delete("all")
            if hasattr(self, "thermal_canvas"):
                self.thermal_canvas.delete("all")
            if hasattr(self, "xfmr_canvas"):
                self.xfmr_canvas.delete("all")
            if hasattr(self, "stage_canvas"):
                self.stage_canvas.delete("all")
            self._set_output_highlights([])
            self._set_feasibility_text([f"ERROR: {ex}"])
            self.status_text.set(f"Input error: {ex}")

    @staticmethod
    def _fmt(value: float) -> str:
        if abs(value) >= 1000 or abs(value) < 0.01:
            return f"{value:.4e}"
        return f"{value:.6g}"


def main() -> None:
    root = tk.Tk()
    app = LLCQuickCalc(root)
    root.app = app  # type: ignore[attr-defined]
    root.mainloop()


if __name__ == "__main__":
    main()
