#!/usr/bin/env python3
"""
Simple GUI front-end for the OpenCells UICC programmer (program_uicc).

What it does
------------
* On start-up it auto-detects the USB card programmer (/dev/ttyUSB* or /dev/ttyACM*).
* Lets you fill in the card fields: ADM, ICCID, IMSI, ISDN, ACC, Ki (key), OPc, SPN.
* The "Write + Verify" button runs the exact same command you would run on the CLI,
  with sudo, and always appends --authenticate so the Milenage algorithm is checked.
* Any error is shown as a clear, formatted pop-up.

Run with:   python3 uicc_gui.py
(Tkinter is required: sudo apt install python3-tk  if it is missing.)
"""

import glob
import os
import re
import shutil
import subprocess
import threading

import tkinter as tk
from tkinter import ttk, messagebox


# --------------------------------------------------------------------------- #
#  Helpers to locate the reader and the program_uicc binary
# --------------------------------------------------------------------------- #
def find_binary():
    """Return the path to the program_uicc binary, or None if not found."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "program_uicc"),
        os.path.join(here, "uicc-v3.3", "program_uicc"),
        os.path.join(os.getcwd(), "program_uicc"),
        os.path.join(os.getcwd(), "uicc-v3.3", "program_uicc"),
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return shutil.which("program_uicc")


def detect_ports():
    """Return a sorted list of likely reader devices."""
    return sorted(glob.glob("/dev/ttyUSB*")) + sorted(glob.glob("/dev/ttyACM*"))


HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def is_hex(s):
    return bool(HEX_RE.match(s))


BINARY = find_binary()


# --------------------------------------------------------------------------- #
#  The fields shown in the form: (key, label, hint, required)
# --------------------------------------------------------------------------- #
FIELDS = [
    ("adm",   "ADM code",      "8 digits (e.g. 12345678) or 16 hex chars", True),
    ("iccid", "ICCID",         "19–20 digits",                              False),
    ("imsi",  "IMSI",          "14–15 digits (MCC+MNC+MSIN)",               False),
    ("isdn",  "MSISDN / ISDN", "phone number digits (optional)",            False),
    ("acc",   "ACC",           "access control class, hex (e.g. 0001)",     False),
    ("key",   "Ki (key)",      "32 hex chars",                              True),
    ("opc",   "OPc",           "32 hex chars",                              True),
    ("spn",   "SPN",           "network name shown by the phone",           False),
]


class UiccGui:
    def __init__(self, root):
        self.root = root
        self.vars = {}
        self.sudo_password = None      # cached for the session
        self.sudo_cached = False
        self.busy = False

        root.title("UICC / SIM programmer")
        root.minsize(640, 560)

        self._build_ui()
        self.refresh_ports()
        self._check_binary()

    # ----------------------------- UI layout ------------------------------- #
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)

        # --- reader row ---
        ttk.Label(main, text="Reader port", font=("", 10, "bold")).grid(
            row=0, column=0, sticky="w", **pad)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(main, textvariable=self.port_var, width=24)
        self.port_combo.grid(row=0, column=1, sticky="we", **pad)
        ttk.Button(main, text="Refresh", command=self.refresh_ports).grid(
            row=0, column=2, sticky="e", **pad)

        ttk.Separator(main, orient="horizontal").grid(
            row=1, column=0, columnspan=3, sticky="we", pady=8)

        # --- card fields ---
        r = 2
        for key, label, hint, required in FIELDS:
            text = label + (" *" if required else "")
            ttk.Label(main, text=text).grid(row=r, column=0, sticky="w", **pad)
            var = tk.StringVar()
            self.vars[key] = var
            ttk.Entry(main, textvariable=var).grid(
                row=r, column=1, sticky="we", **pad)
            ttk.Label(main, text=hint, foreground="#888").grid(
                row=r, column=2, sticky="w", **pad)
            r += 1

        self.vars["spn"].set("OpenCells")   # sensible default

        ttk.Label(main, text="* required   —   the Milenage check (--authenticate) "
                             "always runs on write",
                  foreground="#888").grid(row=r, column=0, columnspan=3,
                                          sticky="w", padx=8, pady=(2, 8))
        r += 1

        # --- buttons ---
        btns = ttk.Frame(main)
        btns.grid(row=r, column=0, columnspan=3, sticky="we", pady=6)
        self.read_btn = ttk.Button(btns, text="Read card",
                                   command=lambda: self.start("read"))
        self.read_btn.pack(side="left")
        self.write_btn = ttk.Button(btns, text="Write + Verify",
                                    command=lambda: self.start("write"))
        self.write_btn.pack(side="right")
        r += 1

        # --- output log ---
        ttk.Label(main, text="Output").grid(row=r, column=0, sticky="w", padx=8)
        r += 1
        log_frame = ttk.Frame(main)
        log_frame.grid(row=r, column=0, columnspan=3, sticky="nsew", padx=8, pady=4)
        main.rowconfigure(r, weight=1)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=10, wrap="word", state="disabled",
                           font=("monospace", 9))
        self.log.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(log_frame, command=self.log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log.config(yscrollcommand=sb.set)
        r += 1

        # --- status bar ---
        self.status = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status, relief="sunken",
                  anchor="w", padding=4).pack(fill="x", side="bottom")

    # --------------------------- small helpers ----------------------------- #
    def _check_binary(self):
        if BINARY is None:
            self.set_status("program_uicc binary NOT found — set it next to this script")
            self.write_btn.state(["disabled"])
            self.read_btn.state(["disabled"])
            messagebox.showerror(
                "Programmer not found",
                "Could not find the 'program_uicc' executable.\n\n"
                "Place this script next to it, or next to the 'uicc-v3.3' folder, "
                "and restart.")
        else:
            self.set_status(f"Ready — using {BINARY}")

    def set_status(self, text):
        self.status.set(text)

    def refresh_ports(self):
        ports = detect_ports()
        self.port_combo["values"] = ports
        if ports:
            if self.port_var.get() not in ports:
                self.port_var.set(ports[0])
            self.set_status(f"Detected reader(s): {', '.join(ports)}")
        else:
            self.port_var.set("")
            self.set_status("No /dev/ttyUSB* reader detected — plug in the programmer "
                            "and press Refresh")

    def values(self):
        return {k: v.get().strip() for k, v in self.vars.items()}

    def log_write(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.config(state="disabled")

    # ----------------------------- validation ------------------------------ #
    def validate(self):
        problems = []
        v = self.values()

        if not self.port_var.get().strip():
            problems.append("• No reader port selected (no /dev/ttyUSB* detected).")

        adm = v["adm"]
        if not adm:
            problems.append("• ADM code is required to write the card.")
        elif len(adm) == 16 and not is_hex(adm):
            problems.append("• ADM code of 16 chars must be hexadecimal.")
        elif len(adm) not in (8, 16):
            problems.append("• ADM code must be 8 digits or 16 hex characters.")

        for key in ("key", "opc"):
            label = "Ki (key)" if key == "key" else "OPc"
            val = v[key]
            if not val:
                problems.append(f"• {label} is required (needed for the Milenage check).")
            elif len(val) != 32 or not is_hex(val):
                problems.append(f"• {label} must be exactly 32 hexadecimal characters "
                                f"(got {len(val)}).")

        if v["iccid"] and not v["iccid"].isdigit():
            problems.append("• ICCID must contain digits only.")
        if v["imsi"]:
            if not v["imsi"].isdigit():
                problems.append("• IMSI must contain digits only.")
            elif len(v["imsi"]) not in (14, 15):
                problems.append("• IMSI is usually 14 or 15 digits.")
        if v["acc"] and not is_hex(v["acc"]):
            problems.append("• ACC must be hexadecimal (e.g. 0001).")
        if v["isdn"] and not v["isdn"].isdigit():
            problems.append("• MSISDN / ISDN must contain digits only.")

        return problems

    # -------------------------- command building --------------------------- #
    def build_args(self, write):
        v = self.values()
        args = ["--port", self.port_var.get().strip()]
        if write:
            args += ["--adm", v["adm"]]
            for k in ("iccid", "imsi", "isdn", "acc", "key", "opc"):
                if v[k]:
                    args += ["--" + k, v[k]]
            if v["spn"]:
                args += ["--spn", v["spn"]]
            args += ["--authenticate"]
        return args

    def masked_cmdline(self, args):
        """Command line for the log, with secrets hidden."""
        secret = {"--adm", "--key", "--opc"}
        out, hide = [], False
        for a in args:
            if hide:
                out.append("****")
                hide = False
            else:
                out.append(a)
                hide = a in secret
        prefix = "" if os.geteuid() == 0 else "sudo "
        return prefix + os.path.basename(BINARY) + " " + " ".join(out)

    # ----------------------------- sudo handling --------------------------- #
    def ensure_sudo(self):
        """Make sure we can run as root. Returns False if the user cancels."""
        if os.geteuid() == 0:
            return True
        if self.sudo_cached:
            return True
        # passwordless sudo?
        try:
            r = subprocess.run(["sudo", "-n", "true"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                self.sudo_password = ""
                self.sudo_cached = True
                return True
        except Exception:
            pass
        pw = self.ask_password()
        if pw is None:
            return False
        self.sudo_password = pw
        self.sudo_cached = True
        return True

    def ask_password(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Administrator password")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        ttk.Label(dlg, text="Enter your password (sudo) to run the programmer:").pack(
            padx=16, pady=(16, 6))
        var = tk.StringVar()
        ent = ttk.Entry(dlg, textvariable=var, show="•", width=32)
        ent.pack(padx=16)
        ent.focus_set()
        result = {"pw": None}

        def ok(*_):
            result["pw"] = var.get()
            dlg.destroy()

        def cancel(*_):
            result["pw"] = None
            dlg.destroy()

        row = ttk.Frame(dlg)
        row.pack(pady=12)
        ttk.Button(row, text="OK", command=ok).pack(side="left", padx=6)
        ttk.Button(row, text="Cancel", command=cancel).pack(side="left", padx=6)
        ent.bind("<Return>", ok)
        dlg.bind("<Escape>", cancel)
        self.root.wait_window(dlg)
        return result["pw"]

    # ------------------------------ execution ------------------------------ #
    def start(self, mode):
        if BINARY is None or self.busy:
            return
        if mode == "write":
            problems = self.validate()
            if problems:
                messagebox.showerror("Please fix these fields",
                                     "\n".join(problems))
                return
        else:
            if not self.port_var.get().strip():
                messagebox.showerror("No reader",
                                     "No reader port selected.\nPlug in the "
                                     "programmer and press Refresh.")
                return

        if not self.ensure_sudo():
            return

        args = self.build_args(write=(mode == "write"))
        self.set_busy(True)
        self.log_write("\n$ " + self.masked_cmdline(args) + "\n")
        threading.Thread(target=self._worker, args=(mode, args),
                         daemon=True).start()

    def set_busy(self, busy):
        self.busy = busy
        state = ["disabled"] if busy else ["!disabled"]
        self.write_btn.state(state)
        self.read_btn.state(state)
        if busy:
            self.set_status("Working…  please do NOT remove the card")
            self.root.config(cursor="watch")
        else:
            self.root.config(cursor="")

    def run_tool(self, args):
        if os.geteuid() == 0:
            cmd = [BINARY] + args
            stdin = None
        else:
            cmd = ["sudo", "-S", "-p", ""] + [BINARY] + args
            stdin = (self.sudo_password or "") + "\n"
        proc = subprocess.run(cmd, input=stdin, capture_output=True,
                             text=True, timeout=240)
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    def _worker(self, mode, args):
        try:
            rc, out, err = self.run_tool(args)
        except subprocess.TimeoutExpired:
            self.root.after(0, lambda: self._done_error(
                "Timeout",
                "The programmer did not respond within the time limit.\n\n"
                "Check that the reader is connected and a card is inserted, "
                "then try again."))
            return
        except Exception as e:                                 # noqa: BLE001
            msg = str(e)
            self.root.after(0, lambda: self._done_error(
                "Could not run the programmer", msg))
            return
        self.root.after(0, lambda: self._done(mode, rc, out, err))

    def _done_error(self, title, message):
        self.set_busy(False)
        self.log_write(f"\n[ERROR] {title}: {message}\n")
        messagebox.showerror(title, message)

    def _done(self, mode, rc, out, err):
        self.set_busy(False)
        if out:
            self.log_write(out if out.endswith("\n") else out + "\n")
        if err:
            self.log_write(err if err.endswith("\n") else err + "\n")

        level, title, message, clear_sudo = self.classify(mode, rc, out, err)
        if clear_sudo:
            self.sudo_cached = False
            self.sudo_password = None
        self.set_status(title)
        if level == "success":
            messagebox.showinfo(title, message)
        elif level == "warning":
            messagebox.showwarning(title, message)
        else:
            messagebox.showerror(title, message)

    # --------------------------- result analysis --------------------------- #
    def classify(self, mode, rc, out, err):
        """Turn the raw tool output into (level, title, message, clear_sudo)."""
        text = out + "\n" + err

        # --- sudo problems ---
        if re.search(r"incorrect password|Sorry, try again|a password is required",
                     err, re.I):
            return ("error", "Wrong system password",
                    "The sudo (administrator) password was not accepted.\n\n"
                    "Please try the operation again and re-enter it.", True)

        # --- reader / port problems (Assert -> abort) ---
        if "Failed to open" in text:
            port = self.port_var.get().strip()
            return ("error", "Card reader not found",
                    f"Could not open the reader on {port}.\n\n"
                    "Please check that:\n"
                    "  • the USB programmer is plugged in\n"
                    "  • the correct port is selected (press Refresh)\n"
                    "  • a card is inserted in the reader", False)

        # --- ADM problems (card NOT modified) ---
        if "chv 0a Nok" in text:
            return ("error", "ADM code rejected",
                    "The card refused the ADM (master) code.\n"
                    "The card was NOT modified.\n\n"
                    "Double-check the ADM code and try again.", False)
        if "No ADM code of 8 figures" in text:
            return ("error", "Invalid ADM code",
                    "The ADM code is not valid.\n"
                    "It must be 8 digits, or 16 hexadecimal characters.", False)

        # --- Milenage authentication problems ---
        if "OPc or Ki is wrong" in text or "didn't accept our challenge" in text:
            return ("error", "Milenage check failed",
                    "The card rejected the authentication challenge.\n\n"
                    "The Ki (key) and/or the OPc do not match the card.\n"
                    "Verify both values (32 hex characters each).", False)
        if "not our milenage computation" in text:
            return ("error", "Milenage mismatch",
                    "The card answered, but the vectors do not match the "
                    "expected Milenage computation.\n\n"
                    "Check the Ki / OPc values.", False)
        m = re.search(r"tried SQN (\d+), but the card refused", text)
        if m:
            return ("error", "Milenage: sequence number refused",
                    f"The card refused the sequence number "
                    f"(tried SQN {m.group(1)}).\n\n"
                    "The Ki/OPc are likely correct but the SQN could not be "
                    "resynchronised. Retry, or check the card.", False)

        # --- generic hard failure (Assert -> abort) ---
        if rc != 0 or "Assertion (" in text:
            extra = re.search(r"additional txt:\s*(.*)", text)
            syserr = re.search(r"System error:\s*(.*)", text)
            detail = extra.group(1).strip() if extra and extra.group(1).strip() else ""
            body = "The programmer stopped with an error."
            if detail:
                body += f"\n\nDetails: {detail}"
            if syserr and syserr.group(1).strip() not in ("", "Success"):
                body += f"\nSystem: {syserr.group(1).strip()}"
            body += "\n\nSee the Output panel for the full log."
            return ("error", "Programming error", body, False)

        # --- success paths ---
        if mode == "read":
            return ("success", "Card read",
                    self._summary(text) or "Card read successfully.\n"
                    "See the Output panel for the values.", False)

        sqn = re.search(r"Succeeded to authentify with SQN:\s*(\d+)", text)
        hss = re.search(r"set HSS SQN value as:\s*(\d+)", text)
        if sqn:
            body = "The card was written and the Milenage check PASSED.\n\n"
            body += self._summary(text)
            body += f"\nCurrent SQN on card: {sqn.group(1)}\n"
            if hss:
                body += f"Set the HSS/UDM SQN value to: {hss.group(1)}\n"
            if "Warning in AUTS" in text:
                body += "\n(Note: an AUTS warning was reported — see log.)"
            return ("success", "Card written and verified", body, False)

        # written but Milenage not confirmed
        return ("warning", "Card written (not fully verified)",
                "The write finished without a fatal error, but the Milenage "
                "authentication result could not be confirmed.\n\n"
                "Check the Output panel for details.", False)

    @staticmethod
    def _summary(text):
        """Pull the human-readable read-back values out of the output."""
        lines = []
        for label, pat in (("ICCID",   r"^ICCID:\s*(.+)$"),
                           ("IMSI",    r"USIM IMSI:\s*(.+)"),
                           ("MSISDN",  r"USIM MSISDN:\s*(.+)"),
                           ("SPN",     r"USIM Service Provider Name:\s*(.+)")):
            m = re.search(pat, text, re.M)
            if m and m.group(1).strip():
                lines.append(f"  {label}: {m.group(1).strip()}")
        return ("Card values:\n" + "\n".join(lines) + "\n") if lines else ""


def main():
    root = tk.Tk()
    UiccGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
