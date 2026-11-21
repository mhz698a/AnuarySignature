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
%LOCALAPPDATA%\\AnuarySignature\\Structure\\__structure__
```

Before the first launch, authenticate to GitHub with an account that has access
to the private repository, then clone it to the expected location:

```powershell
git clone https://github.com/mhz698a/AnuarySignature-Structure.git "$env:LOCALAPPDATA\\AnuarySignature\\Structure"
```

GitHub Desktop can also be used to clone the private repository to that exact
directory. Do not clone it inside the AnuarySignature application directory.

This migration establishes the local data location. Uploading and downloading
updates through AnuarySignature itself will be implemented in a later phase.
Until then, changes to Structure files remain local unless committed and pushed
using Git or GitHub Desktop.

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
