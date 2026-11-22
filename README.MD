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
including the directory tree and references to character credential files.
The report can be generated in either of two independent formats in the
report dialog:

- JSON: \`__structure__/dependent_directory_report.json\`, for structured data.
- TXT: \`__structure__/dependent_directory_report.txt\`, as a plain-text
  directory tree with branches, subfolders and the discovered credential
  filenames.

The inventory includes four-digit year directories and at most two directory
levels below each year. It also scans the album directory identified by the
year prefix and recognizes character folders using AnuarySignature's existing
naming convention. The tree report lists credential filenames under their
character folders and indicates missing or ambiguous credentials. Credential
JSON contents and image files are never opened, copied or embedded.

The exclusion list is derived from the same authoritative source used by
year creation. `folders.json` is preferred whenever it is a valid non-empty
object. If it is unavailable or invalid, the report uses the same fallback
template priority as year creation: current year, previous year, then the
maximum existing year. If no template exists, it uses the same minimal
fallback categories as year creation.

The Qt-independent `engines/year_structure.py` module is the shared resolver.
Both `year_visor/year_creator.py` and the report service use its
`folders.json` loader and fallback-template selection, avoiding a separate
hardcoded or first-alphabetical-year definition.

Numeric prefixes are normalized, so entries such as `22. album` and
`23. album` become one `album` category in the exclusion list. The list shows
the category name without the numeric prefix because that prefix is derived
from each year as `max(0, year - 2003)`. Dynamic season names such as
`22. ___[Season 2025]` and `23. ___[Season 2026]` become one
`___[...]` category. Each category appears only once; checking it excludes
matching folders and their subtrees in every year. `resources.local.personal`
remains excluded globally by default.

Every four-digit year is validated against the resolved year-creation
structure, not against the first alphabetically detected year. A missing or
extra category is identified by year and blocks report generation until the
directory structure is corrected.

Global exclusion preferences are stored in
\`__structure__/dependent_directory_report_settings.json\`. Existing version-1
preferences are migrated from year-specific paths to global folder categories
when loaded.

Opening the dialog does not generate a report. Select JSON or TXT and press
**Generar reporte** to start the scan. The progress display identifies the
year and folder currently being processed. The selected output is replaced
atomically only after the scan completes; a failed scan preserves its previous
file. The application may also refresh the report through its existing
background refresh hooks after relevant directory or character-credential
changes.

The report and its exclusion preferences are local changes in the private
Structure repository. Use the usual
**Ajustes → Sincronizar Structure con GitHub → Subir cambios** action to
publish them.

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
