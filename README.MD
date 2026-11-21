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
Manager or GitHub Desktop.

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
