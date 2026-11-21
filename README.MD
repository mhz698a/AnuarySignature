# 📘 AnuarySignature

A Python application for viewing and analyzing domain information and create notes for her.

## Features

- Domain information lookup
- Easy-to-use interface
- Fast and reliable

## Prerequisites

- Python 3.7 or higher

## Private Structure data repository

AnuarySignature keeps its shared JSON data in the private repository
[AnuarySignature-Structure](https://github.com/mhz698a/AnuarySignature-Structure).
The application reads these files from:

```text
%LOCALAPPDATA%\AnuarySignature\Structure\__structure__
```

Before the first launch, authenticate to GitHub with an account that has access
to the private repository, then clone it to the expected location:

```powershell
git clone https://github.com/mhz698a/AnuarySignature-Structure.git "$env:LOCALAPPDATA\AnuarySignature\Structure"
```

GitHub Desktop can also be used to clone the private repository to that exact
directory. Do not clone it inside the AnuarySignature application directory.

## Synchronization and local backups

Use **Ajustes → Sincronizar Structure con GitHub** to check for remote updates,
download changes, or upload local edits. Downloads use fast-forward updates only
and create a local backup before changing files. Local modifications and diverged
commits are never overwritten automatically.

Local backups are stored outside the Git checkout at:

```text
%LOCALAPPDATA%\\AnuarySignature\\Backups\\Structure
```

The synchronization controls require Git to be installed and the private
repository to be accessible through the account configured in Git Credential
Manager or through a token registered in **Administrar token**.

For token authentication, create a **fine-grained personal access token** for
the `mhz698a` resource owner and select only the
`AnuarySignature-Structure` repository. Grant **Contents: Read and write**
(Metadata: Read is required by GitHub). Register the token in the sync dialog.
The secret is stored in Windows Credential Manager, not in the source tree or
the Structure JSON files. The expiration date shown in the application is the
date entered by the user when registering the token; GitHub does not expose
that PAT expiration date through the normal token validation response.

Git operations run without opening visible Windows console windows. The
**Subir cambios** action commits local Structure edits and pushes them to
`main` only when the remote branch has no commits waiting to be downloaded.

## Dependent-drive directory report

AnuarySignature can generate an inventory of the configured dependent drive,
including directory structure and references to character credential files.
The report is stored in the private Structure checkout at:

```text
__structure__/dependent_directory_report.json
```

The directory inventory includes four-digit year directories and at most two
directory levels below each year. For example, it records `2009`,
`2009\\06. music`, and `2009\\06. music\\06. s.rt.example`.
The report also scans each year's `album` folder identified by the year prefix and recognizes
character folders using AnuarySignature's existing naming convention. It records
the character identity, the relative folder path, the credential filename and
the credential's relative path. Missing credentials are marked as missing;
multiple `__*.json` candidates are marked as ambiguous unless the standard
`__CharacterName__.json` filename identifies the credential unambiguously.

Credential JSON contents and image files are never opened, copied or embedded
in this report. Only regular credential filenames and relative paths are
recorded. Symbolic links and Windows reparse-point files/directories are skipped.

The report is regenerated after AnuarySignature creates a year, creates a
shared year folder, renames a year folder, or creates a missing identity
directory while saving a year credential. To rebuild it manually, use
**Herramientas → Generar/actualizar reporte de la unidad dependiente**.
The manual scan runs in the background and preserves the previous report if
the dependent drive cannot be read completely.

The report is a local change in the private Structure repository. Use
**Ajustes → Sincronizar Structure con GitHub → Subir cambios** to publish the
updated report to the private repository so it can be consulted remotely.

## Phase 6 — Structure status and character colours

The main window status bar shows the private Structure Git state to the right
of the zoom percentage. It polls in the background every three minutes and
distinguishes remote commits to pull, local commits to push, uncommitted local
changes, conflicts, a non-main branch, a clean/synchronized state and connection
errors. The monitor pauses while the synchronization dialog is active and
refreshes after it closes. Each background fetch has a 15-second timeout.

Character theme colours use the existing `color_group` and
`secondary_color` fields. The private Structure repository contains a companion
source manifest at `__structure__/character_color_references.json`; no
`fandom` attribute is added to character records. `dorado` is supported as a
distinct palette value. During character scans, researched Structure colours
are copied to local character credentials only when those local fields are
empty; non-empty local values remain authoritative.

The researched cache update is reviewed separately in
[AnuarySignature-Structure PR #1](https://github.com/mhz698a/AnuarySignature-Structure/pull/2).

## Phase 7 — Character credential backups

The character cache is an index of paths and metadata; it does not contain the
full individual credential JSON files or image bytes. The actual JSON
credentials remain in the character folders on the dependent drive.

AnuarySignature stores a replaceable backup for each character under
`__structure__/character_credentials/<year>/<alterego>--<name>/` in the private
Structure checkout. Each entry contains the original credential JSON, the
selected `icon_path` image, the selected `background_path` image when present,
and a manifest with hashes and source-relative metadata.

Saving a character automatically refreshes that character's local Structure
backup. To back up every character credential on disk (not only the profiles
currently represented in the UI cache), use
**Herramientas → Respaldar credenciales de personajes en Structure**. The scan
locates character folders under each year's album directory and copies only the
credential JSON plus its selected icon/background resources.
Image changes replace the previous backup copy in that character's archive
folder; they never delete or alter the source image in the dependent drive.
Only selected icon/background assets are copied, not every image in the folder.
The bulk backup runs in a worker thread.

The backup first writes into the local private Structure checkout. It is not
pushed automatically, because an automatic push could publish other pending
Structure changes. Review the statusbar and use **Subir cambios** to publish it.

## Phase 8 — Approval-gated orders from GitHub or AI

Orders are JSON files placed in the private Structure repository under
`__structure__/orders/pending/<order-id>.json`. An AI can propose an order by
opening a Pull Request in that private repository. After review and merge, the
user downloads Structure and opens
**Herramientas → Revisar órdenes de GitHub**.

No order runs automatically. The application validates the operation and
target, previews the affected character/path, and requires an explicit
**Aplicar orden** confirmation. Supported operations are:
`update_character_credential`, `replace_character_asset`, `update_dependent_json`, and
`create_directory`. Existing JSON files receive a pre-change backup under
`%LOCALAPPDATA%\\AnuarySignature\\Backups\\DependentOrders`. Applied order
IDs are tracked locally so they cannot be repeated on the same computer.

There are no delete, move, rename, shell, script or arbitrary-code operations.
An order cannot write outside the configured dependent drive. Changing an image path directly requires that the referenced image already exist
inside the dependent drive. The separate `replace_character_asset` operation can
copy an image delivered in `__structure__/orders/assets/` into a character folder
with a new order-specific filename; it preserves the previous local image and
updates only the selected `icon_path` or `background_path`.
Application results are written to
`__structure__/orders/results/<order-id>.json` and can be published with the
usual **Subir cambios** action.

See [docs/STRUCTURE_ORDERS.md](docs/STRUCTURE_ORDERS.md) for the order schema
and full workflow.

## Synchronization branches and local credentials

Structure synchronization works against the selected remote branch, including the
source branch of a Pull Request hosted in the same repository. After pulling
character metadata, use **Herramientas → Aplicar cambios de caché a credenciales
locales** to compare Structure values against the actual local credential JSONs,
review field differences, and apply selected changes with a pre-change backup.

See [docs/STRUCTURE_BRANCH_AND_CREDENTIAL_SYNC.md](docs/STRUCTURE_BRANCH_AND_CREDENTIAL_SYNC.md)
for the branch workflow, snapshot handling, safety checks and backup locations.

## Installation

1. Clone the repository:
```bash
git clone https://github.com/mhz698a/DomainViewer.git
cd DomainViewer
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

## Project Structure

```
DomainViewer/
├── README.md
├── requirements.txt
├── .gitignore
└── main.py
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

mhz698a
