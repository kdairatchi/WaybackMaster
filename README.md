# WaybackMaster - Advanced Internet Archive Explorer

WaybackMaster is a powerful command-line tool designed to explore and retrieve archived content from the Internet Archive's Wayback Machine. This tool allows you to discover, filter, and analyze historical snapshots of websites with advanced features for both casual users and digital forensics professionals.

![image](https://github.com/user-attachments/assets/39aac02e-4cc0-4a37-8b6f-add3e1fb8cc0)

## Features

- **Interactive Interface**: Rich, colorful, and user-friendly console interface
- **Single or Batch Domain Processing**: Scan one domain or multiple domains from a file
- **File Extension Filtering**: Focus on specific file types (documents, media, archives, etc.)
- **Advanced Wayback API Integration**: Efficient data retrieval with rate limiting and error handling
- **Snapshot Discovery**: Find and verify archived snapshots of discovered URLs
- **Multi-threaded Processing**: Concurrent operations for faster scanning 
- **Automatic HTML Reports**: Generate detailed reports with statistics and clickable links
- **File Download Capability**: Option to automatically download archived files
- **Archive Timeline Analysis**: View content changes over time
- **Customizable Settings**: Configure directory paths, thread count, rate limits, and more

## Installation

### Prerequisites

- Python 3.7+
- pip (Python package manager)

### Quick Install

```bash
# Clone the repository
git clone https://github.com/kdairatchi/waybackmaster.git
cd waybackmaster

# Install required dependencies
pip install -r requirements.txt
```

### Dependencies

- requests
- colorama
- rich
- tqdm
- concurrent.futures (standard library)

## Usage

### Basic Usage

```bash
python waybackmaster.py
```

Running the script will launch the interactive menu system. From there, you can:

1. **Scan a Single Domain**: Enter a domain name to scan
2. **Scan Multiple Domains**: Process a batch of domains from a file
3. **Manage File Extensions**: Configure which file types to look for
4. **Adjust Settings**: Modify program settings and preferences
5. **View Results**: Browse and analyze previous scan results

### File Extensions

The tool uses a file (`extensions.txt`) to define which file types to search for. You can:

- Add custom extensions
- Use predefined sets (documents, media, web files, archives)
- Edit the file directly to add comments or organize extensions

Example `extensions.txt`:
```
# Document types
pdf
doc
docx
xlsx
ppt

# Archive types
zip
rar
7z

# Media
mp4
jpg
png
```

### Output

WaybackMaster creates a structured output directory:
