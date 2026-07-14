# UICC / SIM Card Programmer

A tool to **read and program UICC (SIM/USIM) cards** for private mobile networks
(4G/5G lab setups such as OpenAirInterface, srsRAN, Open5GS, free5GC…).

It is built on the **OpenCells `program_uicc`** command-line tool
(© Laurent Thomas, Open Cells Project — GPL v2) and adds a **simple graphical
interface** (`uicc_gui.py`) on top of it so cards can be written without typing
long command lines.

---

## Table of contents

- [What it does](#what-it-does)
- [Requirements](#requirements)
- [Project layout](#project-layout)
- [Building the CLI tool](#building-the-cli-tool)
- [The graphical interface (recommended)](#the-graphical-interface-recommended)
- [The command-line tool](#the-command-line-tool)
- [Field reference](#field-reference)
- [Milenage authentication & SQN](#milenage-authentication--sqn)
- [Troubleshooting](#troubleshooting)
- [License & credits](#license--credits)

---

## What it does

A UICC ("SIM card") is a small smartcard containing a filesystem. To let a phone
attach to a mobile network, the card must hold a matching **identity** (IMSI,
ICCID) and a **shared secret** (the `Ki` key and the `OPc` operator key). The
same secrets must also be configured in the network core (HSS / UDM).

This tool talks to the card through a USB reader using the smartcard **APDU**
protocol and writes those fields. Programming the protected fields requires the
card's **ADM key** (its master password).

The program can:

- **Read** the current values stored on a card (IMSI, ICCID, MSISDN, PLMN, SPN…).
- **Write** a full set of identity and security fields.
- **Verify** the card with the **Milenage** authentication algorithm and recover
  the card's current **sequence number (SQN)**.

---

## Requirements

- Linux (developed/tested on Ubuntu 22.04).
- A USB smartcard reader that exposes a serial device (`/dev/ttyUSB*`), or a
  PC/SC reader (see the PC/SC note below).
- Programmable UICC cards **with a known ADM key** (blank/programmable "sysmoUSIM",
  "OpenCells" or similar test cards).
- To **build** the CLI tool: `g++`, `make`.
- To run the **GUI**: `python3` and `python3-tk` (Tkinter).
- `sudo` rights (needed to access the reader device).

Install the basics on Debian/Ubuntu:

```bash
sudo apt update
sudo apt install build-essential python3 python3-tk
```

---

## Project layout

```
uicc_programmer/
├── README.md                  ← this file
├── uicc_gui.py                ← the graphical interface (Python/Tkinter)
└── uicc-v3.3/
    ├── program_uicc.c         ← main CLI program (orchestration + options)
    ├── uicc.h                 ← APDU protocol, file tables, encoding helpers
    ├── milenage.h             ← Milenage (3GPP AKA) algorithm
    ├── aes.h                  ← AES used by Milenage
    ├── Makefile               ← build rules
    ├── REAME.txt              ← original OpenCells notes
    ├── program_uicc           ← the compiled raw-reader binary
    └── program_uicc_pcsc      ← PC/SC-reader binary (prebuilt; may need rebuild)
```

---

## Building the CLI tool

> **Important:** the binary shipped inside the archive was compiled on a newer
> distribution and may fail to start on Ubuntu 22.04 with:
>
> ```
> program_uicc: /lib/x86_64-linux-gnu/libstdc++.so.6: version `GLIBCXX_3.4.32' not found
> ```
>
> This means the prebuilt binary needs a newer `libstdc++` than your system
> provides. **Recompiling it locally fixes it** — the rebuilt binary links
> against your own libstdc++.

Build the raw-reader version:

```bash
cd uicc-v3.3
rm -f program_uicc      # remove any stale/prebuilt binary first
make
```

This produces the `program_uicc` executable, used by both the CLI and the GUI.

### PC/SC readers (optional)

If you use a standard PC/SC reader (e.g. a Gemalto GemPC Twin) instead of a raw
serial reader, build the PC/SC variant:

```bash
sudo apt install libpcsclite-dev libccid
cd uicc-v3.3
make program_uicc_pcsc
```

You may need to adapt the library path in the `Makefile` to your distribution.

---

## The graphical interface (recommended)

The GUI wraps the CLI so you can fill in fields and click a button.

### Run it

```bash
python3 uicc_gui.py
```

(Run it as your normal user — it will ask for your `sudo` password when needed.)

### Features

- **Automatic reader detection** — on start it scans for `/dev/ttyUSB*` (and
  `/dev/ttyACM*`) and pre-selects the port. A **Refresh** button re-scans if you
  plug the reader in afterwards. The port box is editable for manual entry.
- **Card fields**: ADM, ICCID, IMSI, ISDN/MSISDN, ACC, Ki (key), OPc, SPN, each
  with an inline hint. Required fields are marked with `*`.
- **Write + Verify** button — builds and runs the exact CLI command with `sudo`
  and **always adds `--authenticate`**, so the Milenage algorithm is checked on
  every write.
- **Read card** button — reads and displays the current card values (no ADM
  needed).
- **Clear error pop-ups** — the tool's raw output is translated into readable
  messages, for example:
  - ADM rejected → *"ADM code rejected — the card was NOT modified."*
  - Reader missing → *"Card reader not found"* with a checklist.
  - Wrong keys → *"Milenage check failed — Ki and/or OPc do not match."*
  - On success it shows the read-back identity plus the **SQN** and the
    *"set HSS/UDM SQN value to: N"* hint.
- **Input validation** before writing (e.g. Ki/OPc must be 32 hex characters,
  ADM must be 8 digits or 16 hex, IMSI must be digits…). All problems are listed
  in a single pop-up.
- **Output panel** with the full log; secret values (ADM/Ki/OPc) are masked in
  the displayed command line.
- **`sudo` handling** — asks for the password once per session (or detects
  passwordless sudo). The GUI itself runs as a normal user; only the card
  command is elevated.

> Tkinter missing? Install it with `sudo apt install python3-tk`.

---

## The command-line tool

The GUI calls this underneath; you can also use it directly.

### Read a card

Just provide the port (no ADM required):

```bash
sudo ./program_uicc --port /dev/ttyUSB0
```

### Program a card

```bash
sudo ./program_uicc --port /dev/ttyUSB0 \
  --adm 12345678 \
  --iccid 89860061100000000123 \
  --imsi 208920100001123 \
  --isdn 0000012 \
  --acc 0001 \
  --key 6874736969202073796d4b2079650a73 \
  --opc 504f20634f6320504f50206363500a4f \
  --spn OpenCells \
  --authenticate
```

The tool first prints the existing card values, writes the new ones, reads them
back to confirm, and (with `--authenticate`) runs the Milenage check.

### Finding the port

For a raw serial reader it is usually `/dev/ttyUSB0`. If unsure, run `dmesg`
right after plugging the reader in and look for the `ttyUSB` number.
For PC/SC readers use `lsusb` and pass e.g. `--port usb:08e6/3437`
(note the `:` becomes `/`), running the `program_uicc_pcsc` binary.

---

## Field reference

| Option          | Meaning |
|-----------------|---------|
| `--port`        | Reader device (default `/dev/ttyUSB0`). |
| `--adm`         | **ADM master password** — required to write. 8 digits, or 16 hex chars. |
| `--iccid`       | Integrated Circuit Card ID (the card serial number). |
| `--imsi`        | Subscriber identity. The tool auto-fills related files (home PLMN, etc.). |
| `--isdn`        | MSISDN (phone number). Not needed for basic 4G attach. |
| `--acc`         | Access Control Class. |
| `--key`         | **Ki** — the 128-bit authentication key (32 hex chars). Must match the HSS/UDM. |
| `--opc`         | **OPc** — operator key derived value (32 hex chars). Must match the core. |
| `--xx`          | **OP** instead of OPc (exclusive with `--opc`); the tool computes OPc from OP + Ki. |
| `--spn`         | Service Provider Name shown by the phone (default *"open cells"*). |
| `--acc`         | Access control class code. |
| `--MNCsize`     | Mobile Network Code length in digits (default 2). |
| `--act`         | Bitmap of supported radio access technologies (default `7c00`, see TS 31.102). |
| `--ust`         | USIM service table, in hex. |
| `--authenticate`| Run the Milenage check and discover the current SQN. |
| `--noreadafter` | Do not read the card back after writing. |
| `--sqn`, `--rand` | Test/debug only: print a generated AUTN, no card dialog. |

> **Ki and OPc are the heart of it.** These two secrets, written into the card
> *and* configured identically in your network core, are what let the phone
> authenticate. Keep them safe.

---

## Milenage authentication & SQN

When `--authenticate` is used (the GUI always does), the tool runs the **3GPP AKA
/ Milenage** exchange against the card:

1. If you passed `--xx` (OP), it first computes **OPc** from `OP` + `Ki`.
2. It sends a random challenge (RAND) and, on the first attempt, deliberately
   triggers a resync so the card returns its **AUTS** token.
3. From AUTS it extracts the card's current **sequence number (SQN)**, increments
   it per 3GPP TS 33.102, and re-authenticates.
4. If the card's returned vectors (RES/CK/IK) match the tool's own computation,
   it prints:

   ```
   Succeeded to authentify with SQN: N
   set HSS SQN value as: N+32
   ```

Use the **"set HSS SQN value as"** number in your core network (HSS/UDM) so the
sequence numbers stay in sync and the phone does not get authentication
(resync) failures.

---

## Troubleshooting

**`GLIBCXX_3.4.32 not found` when starting the tool**
The prebuilt binary was compiled for a newer system. Rebuild it locally:
```bash
cd uicc-v3.3 && rm -f program_uicc && make
```
See [Building the CLI tool](#building-the-cli-tool).

**No reader detected / `Failed to open /dev/ttyUSB0`**
- Is the programmer plugged in? Check with `ls /dev/ttyUSB*` or `dmesg`.
- In the GUI, press **Refresh** and pick the right port.
- Is a card actually inserted in the reader?

**Permission denied on the reader**
Access to `/dev/ttyUSB*` needs root or membership of the `dialout` group. The
tool is run with `sudo` for this reason. To avoid sudo, add yourself to the
group: `sudo usermod -aG dialout $USER` (then log out and back in).

**`chv 0a Nok` / "ADM code rejected"**
The ADM (master) code is wrong. The card was **not** modified. Double-check the
ADM value for your specific cards.

**"Milenage check failed" / "OPc or Ki is wrong"**
The `Ki` and/or `OPc` written do not match what the card expects, or do not match
each other. Verify both values (32 hex characters each).

**GUI won't start: `No module named tkinter`**
```bash
sudo apt install python3-tk
```

---

## License & credits

- Core tool: **`program_uicc`** by **Laurent Thomas, Open Cells Project**,
  released under the **GNU General Public License v2** (see the header in
  `uicc-v3.3/program_uicc.c`). Original notes are in `uicc-v3.3/REAME.txt`.
- The `uicc_gui.py` graphical wrapper is provided as a convenience front-end to
  that tool.

This software writes cryptographic secrets to hardware. Use it only with cards
and networks you own or are authorized to provision.
