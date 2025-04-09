import os
import sys
import requests
import time
import json
import concurrent.futures
import logging
from datetime import datetime
from tqdm import tqdm
from colorama import init, Fore, Style
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich.logging import RichHandler
from rich.prompt import Prompt, Confirm
from rich import box

# Initialize colorama and rich console
init(autoreset=True)
console = Console()

# Configure logging with rich
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)]
)
logger = logging.getLogger("wayback_master")

# Constants
VERSION = "2.0"
USER_AGENT = f"WaybackMaster/{VERSION} (https://github.com/waybackmaster/tool)"
API_RATE_LIMIT = 5  # seconds between API calls
MAX_WORKERS = 10    # Max number of concurrent threads
DEFAULT_EXTENSIONS_FILE = "extensions.txt"
DEFAULT_OUTPUT_DIR = "wayback_archives"
CONFIG_FILE = "wayback_master_config.json"

# Banner art with Rich
def display_banner():
    banner = """
    __        __              _                _      __  __           _            
    \\ \\      / /_ _ _   _  | |__   __ _  ___| | __ |  \\/  | __ _ ___| |_ ___ _ __ 
     \\ \\ /\\ / / _` | | | | | '_ \\ / _` |/ __| |/ / | |\\/| |/ _` / __| __/ _ \\ '__|
      \\ V  V / (_| | |_| | | |_) | (_| | (__|   <  | |  | | (_| \\__ \\ ||  __/ |   
       \\_/\\_/ \\__,_|\\__, | |_.__/ \\__,_|\\___|_|\\_\\ |_|  |_|\\__,_|___/\\__\\___|_|   
                    |___/                                                         
    """
    console.print(Panel(
        Text(banner, style="bold blue"),
        subtitle=f"[bold green]v{VERSION} - Advanced Internet Archive Explorer[/]",
        subtitle_align="center",
        box=box.DOUBLE
    ))
    console.print(f"[italic cyan]Developed with ♥ by Kdairatchi (Enhanced Edition)[/]", justify="center")
    console.print()

# Configuration management
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning("Config file is corrupted, using default settings")
    return {
        "default_extensions": [],
        "output_directory": DEFAULT_OUTPUT_DIR,
        "max_workers": MAX_WORKERS,
        "api_rate_limit": API_RATE_LIMIT,
        "check_wayback_snapshots": True,
        "download_files": False,
        "recent_domains": []
    }

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

# Load extensions from file
def load_extensions_from_file(file_path=DEFAULT_EXTENSIONS_FILE):
    try:
        with open(file_path, 'r') as f:
            extensions = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
        return extensions
    except FileNotFoundError:
        logger.warning(f"{file_path} not found. Creating empty file.")
        os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)
        with open(file_path, 'w') as f:
            f.write("# Add one file extension per line (without the dot)\n")
            f.write("# Example:\n")
            f.write("# pdf\n# zip\n# doc\n# xls\n")
        return []

# Load domains from file
def load_domains_from_file(file_path):
    try:
        with open(file_path, 'r') as f:
            domains = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
        return domains
    except FileNotFoundError:
        logger.error(f"{file_path} not found.")
        return None

# Advanced URL fetching with error handling and rate limiting
def fetch_urls(target, config, output_dir):
    archive_url = f'https://web.archive.org/cdx/search/cdx?url=*.{target}/*&output=json&fl=original,timestamp&collapse=urlkey&page=/'
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[bold]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task = progress.add_task(f"[cyan]Fetching URLs for {target}...", total=None)
        
        max_retries = 5
        retry_delay = config["api_rate_limit"]
        attempt = 0
        
        while attempt < max_retries:
            try:
                headers = {
                    'User-Agent': USER_AGENT
                }
                
                with requests.get(archive_url, headers=headers, stream=True, timeout=120) as response:
                    response.raise_for_status()
                    
                    # Parse the JSON response line by line
                    url_data = []
                    line_count = 0
                    
                    for line in response.iter_lines(decode_unicode=True):
                        if line:
                            try:
                                data = json.loads(line)
                                if line_count == 0:  # Skip header row
                                    progress.update(task, total=1000)  # Initial estimate
                                else:
                                    url_data.append(data)
                                line_count += 1
                                
                                if line_count % 100 == 0:
                                    progress.update(task, completed=line_count-1, refresh=True)
                            except json.JSONDecodeError:
                                continue
                    
                    # Successful fetch
                    progress.update(task, completed=line_count, total=line_count)
                    
                    # Process and organize the data
                    results = {}
                    for item in url_data:
                        if len(item) >= 2:  # Ensure we have [url, timestamp]
                            url = item[0]
                            timestamp = item[1] if len(item) > 1 else None
                            
                            # Extract file extension
                            path = url.split('?')[0].split('#')[0]  # Remove query params and fragments
                            ext = os.path.splitext(path)[1].lower()
                            
                            if ext:
                                ext = ext[1:]  # Remove the dot
                                if ext not in results:
                                    results[ext] = []
                                
                                # Add URL with timestamp
                                results[ext].append({
                                    'url': url,
                                    'timestamp': timestamp,
                                    'archived_url': f'https://web.archive.org/web/{timestamp}/{url}' if timestamp else None
                                })
                    
                    return results
                    
            except requests.exceptions.RequestException as e:
                attempt += 1
                if attempt < max_retries:
                    logger.warning(f"Attempt {attempt} failed: {e}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Error fetching URLs after {max_retries} attempts: {e}")
                    logger.info("The server may be rate-limiting or refusing connections.")
                    
                    # Ask if user wants to wait longer and try again
                    if Confirm.ask("Would you like to wait 2 minutes and try again?"):
                        logger.info("Waiting 2 minutes before retrying...")
                        time.sleep(120)
                        attempt = 0  # Reset attempt counter
                        retry_delay = config["api_rate_limit"]  # Reset delay
                    else:
                        return {}

# Improved snapshot checker with concurrent processing
def check_wayback_snapshots(urls, config):
    if not urls:
        return []
    
    results = []
    
    # Define the worker function for concurrent processing
    def check_snapshot(url_data):
        url = url_data['url']
        wayback_url = f'https://archive.org/wayback/available?url={url}'
        
        try:
            headers = {'User-Agent': USER_AGENT}
            response = requests.get(wayback_url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if "archived_snapshots" in data and "closest" in data["archived_snapshots"]:
                snapshot = data["archived_snapshots"]["closest"]
                snapshot_url = snapshot.get("url")
                status = snapshot.get("status")
                timestamp = snapshot.get("timestamp")
                
                if snapshot_url and status == "200":
                    url_data['snapshot_url'] = snapshot_url
                    url_data['snapshot_timestamp'] = timestamp
                    return True, url_data
            
            return False, url_data
            
        except Exception as e:
            logger.debug(f"Error checking snapshot for {url}: {e}")
            return False, url_data
    
    # Use thread pool for concurrent checks
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold green]{task.description}"),
        BarColumn(),
        TextColumn("[bold]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[yellow]Checking archived snapshots...", total=len(urls))
        
        # Process in smaller batches to avoid overwhelming the API
        batch_size = 20
        for i in range(0, len(urls), batch_size):
            batch = urls[i:i+batch_size]
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(config['max_workers'], len(batch))) as executor:
                future_to_url = {executor.submit(check_snapshot, url): url for url in batch}
                
                for future in concurrent.futures.as_completed(future_to_url):
                    success, url_data = future.result()
                    results.append(url_data)
                    progress.update(task, advance=1)
                    
                    # Be nice to the API
                    time.sleep(0.2)
    
    return results

# File downloader function
def download_file(url_data, output_dir, domain):
    url = url_data.get('snapshot_url') or url_data.get('archived_url') or url_data.get('url')
    if not url:
        return False, None
    
    try:
        # Extract filename from URL
        path = url.split('?')[0].split('#')[0]
        filename = os.path.basename(path)
        
        # Create domain directory if it doesn't exist
        domain_dir = os.path.join(output_dir, domain, "downloads")
        os.makedirs(domain_dir, exist_ok=True)
        
        # Destination path
        dest_path = os.path.join(domain_dir, filename)
        
        # Download the file
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        # Get content length for progress reporting
        total_size = int(response.headers.get('content-length', 0))
        
        # Write the file
        with open(dest_path, 'wb') as f:
            if total_size > 0:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=filename) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            else:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        
        return True, dest_path
        
    except Exception as e:
        logger.debug(f"Error downloading {url}: {e}")
        return False, None

# Save filtered URLs with enhanced metadata
def save_filtered_urls(domain, extension_data, output_dir):
    if not extension_data:
        return []
    
    # Create directory structure
    domain_dir = os.path.join(output_dir, domain)
    os.makedirs(domain_dir, exist_ok=True)
    
    all_filtered_urls = []
    
    # For the summary report
    extension_stats = {}
    
    for ext, urls in extension_data.items():
        if urls:
            # Sort URLs by timestamp (newest first if available)
            sorted_urls = sorted(urls, key=lambda x: x.get('timestamp', '0'), reverse=True)
            
            # Save JSON and TXT formats
            json_path = os.path.join(domain_dir, f"{domain}_{ext}_urls.json")
            txt_path = os.path.join(domain_dir, f"{domain}_{ext}_urls.txt")
            
            with open(json_path, 'w') as json_file:
                json.dump(sorted_urls, json_file, indent=2)
            
            with open(txt_path, 'w') as txt_file:
                for url_data in sorted_urls:
                    txt_file.write(f"{url_data['url']}\n")
            
            # Add to all filtered URLs
            all_filtered_urls.extend(sorted_urls)
            
            # Record stats
            extension_stats[ext] = len(sorted_urls)
            
            logger.info(f"Found {len(sorted_urls)} {ext} files for {domain}")
    
    # Create a summary report
    stats_path = os.path.join(domain_dir, f"{domain}_summary.json")
    
    summary = {
        "domain": domain,
        "scan_date": datetime.now().isoformat(),
        "total_urls": len(all_filtered_urls),
        "extensions": extension_stats
    }
    
    with open(stats_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    return all_filtered_urls

# Enhanced domain processing function
def process_domain(domain, extensions, config):
    output_dir = config["output_directory"]
    domain_dir = os.path.join(output_dir, domain)
    
    console.rule(f"[bold cyan]Processing {domain}")
    
    # Create a new session for persistent connections
    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})
    
    # Fetch URLs from Wayback Machine
    extension_data = fetch_urls(domain, config, output_dir)
    
    if not extension_data:
        logger.warning(f"No URLs fetched for {domain}. Skipping...")
        return False
    
    # Filter extensions if specified
    if extensions:
        filtered_data = {ext: urls for ext, urls in extension_data.items() if ext in extensions}
        # Log any extensions that were found but not requested
        extra_exts = set(extension_data.keys()) - set(extensions)
        if extra_exts:
            logger.info(f"Also found files with extensions: {', '.join(extra_exts)}")
    else:
        filtered_data = extension_data
    
    # Save filtered URLs
    all_urls = save_filtered_urls(domain, filtered_data, output_dir)
    
    if config["check_wayback_snapshots"]:
        console.print(f"[green]Checking Wayback Machine snapshots for {len(all_urls)} URLs...")
        urls_with_snapshots = check_wayback_snapshots(all_urls, config)
        
        # Update the saved files with snapshot information
        for ext in filtered_data.keys():
            ext_urls = [u for u in urls_with_snapshots if os.path.splitext(u['url'].split('?')[0])[1].lower()[1:] == ext]
            if ext_urls:
                json_path = os.path.join(domain_dir, f"{domain}_{ext}_urls.json")
                with open(json_path, 'w') as json_file:
                    json.dump(ext_urls, json_file, indent=2)
    
    # Download files if requested
    if config["download_files"]:
        downloadable_urls = [u for u in all_urls if u.get('snapshot_url') or u.get('archived_url')]
        if downloadable_urls:
            console.print(f"[green]Downloading {len(downloadable_urls)} archived files...")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TextColumn("[bold]{task.completed}/{task.total}"),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Downloading files...", total=len(downloadable_urls))
                
                for url_data in downloadable_urls:
                    success, path = download_file(url_data, output_dir, domain)
                    progress.update(task, advance=1)
                    time.sleep(0.5)  # Be nice to the server
    
    # Generate summary and report
    generate_domain_report(domain, filtered_data, domain_dir)
    return True

# Generate an HTML report for the domain
def generate_domain_report(domain, extension_data, domain_dir):
    report_path = os.path.join(domain_dir, f"{domain}_report.html")
    
    # Count files by extension
    extension_counts = {ext: len(urls) for ext, urls in extension_data.items()}
    total_files = sum(extension_counts.values())
    
    # Create table for summary statistics
    table = Table(title=f"Archive Summary for {domain}")
    table.add_column("Extension", style="cyan")
    table.add_column("Count", justify="right", style="green")
    table.add_column("Percentage", justify="right", style="yellow")
    
    for ext, count in sorted(extension_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_files) * 100 if total_files > 0 else 0
        table.add_row(f".{ext}", str(count), f"{percentage:.1f}%")
    
    table.add_row("Total", str(total_files), "100.0%", style="bold")
    
    # Display summary in console
    console.print(table)
    
    # HTML report content
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wayback Master Report - {domain}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #2980b9;
            margin-top: 30px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #3498db;
            color: white;
            font-weight: 600;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        tr:hover {{
            background-color: #f1f1f1;
        }}
        .extensions-table {{
            width: 50%;
            margin-bottom: 30px;
        }}
        .footer {{
            margin-top: 50px;
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
        }}
        .btn {{
            display: inline-block;
            padding: 8px 15px;
            background-color: #3498db;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            transition: background-color 0.3s;
        }}
        .btn:hover {{
            background-color: #2980b9;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Wayback Machine Archive Report</h1>
        <p><strong>Domain:</strong> {domain}</p>
        <p><strong>Report Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>Total Files Found:</strong> {total_files}</p>
        
        <h2>Files by Extension</h2>
        <table class="extensions-table">
            <thead>
                <tr>
                    <th>Extension</th>
                    <th>Count</th>
                    <th>Percentage</th>
                </tr>
            </thead>
            <tbody>
    """
    
    # Add extension rows
    for ext, count in sorted(extension_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_files) * 100 if total_files > 0 else 0
        html_content += f"""
                <tr>
                    <td>.{ext}</td>
                    <td>{count}</td>
                    <td>{percentage:.1f}%</td>
                </tr>
        """
    
    html_content += f"""
                <tr>
                    <td><strong>Total</strong></td>
                    <td><strong>{total_files}</strong></td>
                    <td><strong>100.0%</strong></td>
                </tr>
            </tbody>
        </table>
        
        <h2>Available Files</h2>
    """
    
    # Add sections for each extension
    for ext, urls in sorted(extension_data.items(), key=lambda x: len(x[1]), reverse=True):
        if urls:
            html_content += f"""
        <h3>.{ext} Files ({len(urls)})</h3>
        <p><a href="{domain}_{ext}_urls.txt" class="btn">Download URL List</a> <a href="{domain}_{ext}_urls.json" class="btn">Download JSON Data</a></p>
        <table>
            <thead>
                <tr>
                    <th>URL</th>
                    <th>Archive Date</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
            """
            
            # Sort URLs by timestamp (newest first if available)
            sorted_urls = sorted(urls, key=lambda x: x.get('timestamp', '0'), reverse=True)
            
            # Show first 100 URLs max for performance
            for i, url_data in enumerate(sorted_urls[:100]):
                url = url_data['url']
                timestamp = url_data.get('timestamp', '')
                archived_url = url_data.get('archived_url', '')
                snapshot_url = url_data.get('snapshot_url', '')
                
                formatted_date = ""
                if timestamp:
                    try:
                        # Format the timestamp (YYYYMMDDHHMMSS)
                        year = timestamp[0:4]
                        month = timestamp[4:6]
                        day = timestamp[6:8]
                        formatted_date = f"{year}-{month}-{day}"
                    except:
                        formatted_date = timestamp
                
                html_content += f"""
                <tr>
                    <td>{url}</td>
                    <td>{formatted_date}</td>
                    <td>
                """
                
                if archived_url:
                    html_content += f"""<a href="{archived_url}" target="_blank" class="btn">View Archive</a> """
                if snapshot_url:
                    html_content += f"""<a href="{snapshot_url}" target="_blank" class="btn">View Snapshot</a>"""
                
                html_content += """
                    </td>
                </tr>
                """
            
            if len(sorted_urls) > 100:
                html_content += f"""
                <tr>
                    <td colspan="3">... and {len(sorted_urls) - 100} more files. See the full list in the downloaded files.</td>
                </tr>
                """
            
            html_content += """
            </tbody>
        </table>
            """
    
    html_content += """
        <div class="footer">
            <p>Generated by WaybackMaster - Advanced Internet Archive Explorer</p>
        </div>
    </div>
</body>
</html>
    """
    
    # Write the HTML report
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logger.info(f"Report generated: {report_path}")

# Command-line interface menu
def main_menu():
    config = load_config()
    
    while True:
        console.clear()
        display_banner()
        
        console.print(Panel(
            Text.from_markup(
                "[bold]Main Menu[/]\n\n"
                "1. [cyan]Scan Single Domain[/]\n"
                "2. [cyan]Scan Multiple Domains[/]\n"
                "3. [cyan]Manage File Extensions[/]\n"
                "4. [cyan]Settings[/]\n"
                "5. [cyan]View Results[/]\n"
                "6. [red]Exit[/]"
            ),
            title="WaybackMaster",
            border_style="blue"
        ))
        
        choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4", "5", "6"], default="1")
        
        if choice == "1":
            scan_single_domain(config)
        elif choice == "2":
            scan_multiple_domains(config)
        elif choice == "3":
            manage_extensions(config)
        elif choice == "4":
            settings_menu(config)
        elif choice == "5":
            view_results(config)
        elif choice == "6":
            console.print("[yellow]Exiting WaybackMaster. Goodbye![/]")
            sys.exit(0)

# Scan a single domain
def scan_single_domain(config):
    console.clear()
    display_banner()
    
    # Show recent domains
    if config.get('recent_domains'):
        recent_table = Table(title="Recent Domains")
        recent_table.add_column("Domain", style="cyan")
        
        for domain in config['recent_domains'][-5:]:
            recent_table.add_row(domain)
        
        console.print(recent_table)
        console.print()
    
    domain = Prompt.ask("Enter target domain (e.g., example.com)")
    domain = domain.strip().lower()
    
    # Clean up domain (remove http://, https://, www., etc.)
    if domain.startswith(('http://', 'https://')):
        domain = domain.split('://')[1]
    if domain.startswith('www.'):
        domain = domain[4:]
    if '/' in domain:
        domain = domain.split('/')[0]
    
    # Update recent domains
    if domain not in config.get('recent_domains', []):
        config.setdefault('recent_domains', []).append(domain)
        if len(config['recent_domains']) > 10:
            config['recent_domains'] = config['recent_domains'][-10:]
        save_config(config)
    
    # Ask for extensions
    extensions = select_extensions(config)
    
    # Enhanced options
    console.print(Panel("Advanced Options", border_style="blue"))
    
    config["check_wayback_snapshots"] = Confirm.ask(
        "Check for Wayback Machine snapshots?", 
        default=config.get("check_wayback_snapshots", True)
    )
    
    config["download_files"] = Confirm.ask(
        "Download archived files?", 
        default=config.get("download_files", False)
    )
    
    save_config(config)
    
    # Process the domain
    start_time = time.time()
    success = process_domain(domain, extensions, config)
    end_time = time.time()
    
    if success:
        elapsed = end_time - start_time
        console.print(f"[green]Domain processing completed in {elapsed:.2f} seconds.")
        console.print(f"Results saved to: {os.path.join(config['output_directory'], domain)}")
        
        if Confirm.ask("Open the results folder?", default=True):
            try:
                if sys.platform == 'win32':
                    os.startfile(os.path.join(config['output_directory'], domain))
                elif sys.platform == 'darwin':
                    os.system(f'open "{os.path.join(config["output_directory"], domain)}"')
                else:
                    os.system(f'xdg-open "{os.path.join(config["output_directory"], domain)}"')
            except Exception as e:
                logger.error(f"Could not open folder: {e}")
    
    input("\nPress Enter to return to main menu...")

# Scan multiple domains
def scan_multiple_domains(config):
    console.clear()
    display_banner()
    
    console.print(Panel(
        "Scan multiple domains from a file.\nThe file should contain one domain per line.",
        title="Batch Scanning",
        border_style="blue"
    ))
    
    domain_file = Prompt.ask("Enter the path to the file containing domain list")
    domains = load_domains_from_file(domain_file)
    
    if not domains:
        console.print("[red]No domains found in the file or file not found.[/]")
        input("\nPress Enter to return to main menu...")
        return
    
    console.print(f"[green]Loaded {len(domains)} domains from {domain_file}[/]")
    
    # Show domains and ask for confirmation
    domains_table = Table(title=f"Loaded Domains ({len(domains)})")
    domains_table.add_column("Domain", style="cyan")
    
    for i, domain in enumerate(domains):
        if i < 10:  # Show first 10 domains
            domains_table.add_row(domain)
        elif i == 10:
            domains_table.add_row("...")
    
    console.print(domains_table)
    
    if not Confirm.ask("Proceed with scanning these domains?", default=True):
        console.print("[yellow]Operation cancelled.[/]")
        input("\nPress Enter to return to main menu...")
        return
    
    # Ask for extensions
    extensions = select_extensions(config)
    
    # Enhanced options
    console.print(Panel("Advanced Options", border_style="blue"))
    
    config["check_wayback_snapshots"] = Confirm.ask(
        "Check for Wayback Machine snapshots?", 
        default=config.get("check_wayback_snapshots", True)
    )
    
    config["download_files"] = Confirm.ask(
        "Download archived files?", 
        default=config.get("download_files", False)
    )
    
    save_config(config)
    
    # Process each domain
    start_time = time.time()
    success_count = 0
    
    for i, domain in enumerate(domains):
        console.rule(f"[bold blue]Processing domain {i+1}/{len(domains)}: {domain}")
        try:
            if process_domain(domain, extensions, config):
                success_count += 1
        except Exception as e:
            logger.error(f"Error processing domain {domain}: {e}")
            console.print(f"[red]Failed to process {domain}: {e}[/]")
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    # Summary
    console.print(Panel(
        f"[bold]Batch Processing Complete[/]\n\n"
        f"Total domains: {len(domains)}\n"
        f"Successfully processed: {success_count}\n"
        f"Failed: {len(domains) - success_count}\n"
        f"Total time: {elapsed:.2f} seconds",
        border_style="green"
    ))
    
    if Confirm.ask("Generate a batch summary report?", default=True):
        generate_batch_report(domains, config['output_directory'], success_count)
    
    input("\nPress Enter to return to main menu...")

# Generate a batch summary report
def generate_batch_report(domains, output_dir, success_count):
    report_path = os.path.join(output_dir, "batch_summary_report.html")
    
    # Collect summary data for each domain
    domain_summaries = []
    
    for domain in domains:
        domain_dir = os.path.join(output_dir, domain)
        summary_path = os.path.join(domain_dir, f"{domain}_summary.json")
        
        if os.path.exists(summary_path):
            try:
                with open(summary_path, 'r') as f:
                    summary = json.load(f)
                domain_summaries.append(summary)
            except:
                logger.debug(f"Could not load summary for {domain}")
    
    # Calculate totals
    total_urls = sum(s.get('total_urls', 0) for s in domain_summaries)
    
    # Count extensions across all domains
    all_extensions = {}
    for summary in domain_summaries:
        for ext, count in summary.get('extensions', {}).items():
            all_extensions[ext] = all_extensions.get(ext, 0) + count
    
    # Sort extensions by count
    sorted_extensions = sorted(all_extensions.items(), key=lambda x: x[1], reverse=True)
    
    # HTML report
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WaybackMaster - Batch Scan Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #2980b9;
            margin-top: 30px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #3498db;
            color: white;
            font-weight: 600;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        tr:hover {{
            background-color: #f1f1f1;
        }}
        .summary-table {{
            width: 50%;
            margin-bottom: 30px;
        }}
        .footer {{
            margin-top: 50px;
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
        }}
        .btn {{
            display: inline-block;
            padding: 8px 15px;
            background-color: #3498db;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            transition: background-color 0.3s;
        }}
        .btn:hover {{
            background-color: #2980b9;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Wayback Machine Batch Scan Report</h1>
        <p><strong>Report Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>Total Domains Scanned:</strong> {len(domains)}</p>
        <p><strong>Successfully Processed:</strong> {success_count}</p>
        <p><strong>Failed:</strong> {len(domains) - success_count}</p>
        <p><strong>Total URLs Found:</strong> {total_urls}</p>
        
        <h2>Files by Extension (All Domains)</h2>
        <table class="summary-table">
            <thead>
                <tr>
                    <th>Extension</th>
                    <th>Count</th>
                    <th>Percentage</th>
                </tr>
            </thead>
            <tbody>
    """
    
    # Add extension rows
    for ext, count in sorted_extensions:
        percentage = (count / total_urls) * 100 if total_urls > 0 else 0
        html_content += f"""
                <tr>
                    <td>.{ext}</td>
                    <td>{count}</td>
                    <td>{percentage:.1f}%</td>
                </tr>
        """
    
    html_content += f"""
                <tr>
                    <td><strong>Total</strong></td>
                    <td><strong>{total_urls}</strong></td>
                    <td><strong>100.0%</strong></td>
                </tr>
            </tbody>
        </table>
        
        <h2>Domain Summaries</h2>
        <table>
            <thead>
                <tr>
                    <th>Domain</th>
                    <th>Total URLs</th>
                    <th>File Types</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
    """
    
    # Add domain rows
    for domain in domains:
        domain_dir = os.path.join(output_dir, domain)
        report_path = os.path.join(domain_dir, f"{domain}_report.html")
        summary_path = os.path.join(domain_dir, f"{domain}_summary.json")
        
        if os.path.exists(summary_path):
            try:
                with open(summary_path, 'r') as f:
                    summary = json.load(f)
                    
                total_urls = summary.get('total_urls', 0)
                extensions = summary.get('extensions', {})
                extension_list = ", ".join(f".{ext} ({count})" for ext, count in list(extensions.items())[:5])
                
                if len(extensions) > 5:
                    extension_list += f", and {len(extensions) - 5} more"
                
                html_content += f"""
                <tr>
                    <td>{domain}</td>
                    <td>{total_urls}</td>
                    <td>{extension_list}</td>
                    <td>
                """
                
                if os.path.exists(report_path):
                    rel_path = os.path.relpath(report_path, output_dir)
                    html_content += f"""<a href="{rel_path}" class="btn">View Report</a>"""
                
                html_content += """
                    </td>
                </tr>
                """
            except:
                html_content += f"""
                <tr>
                    <td>{domain}</td>
                    <td colspan="3">Processing failed or incomplete</td>
                </tr>
                """
        else:
            html_content += f"""
            <tr>
                <td>{domain}</td>
                <td colspan="3">Processing failed or incomplete</td>
            </tr>
            """
    
    html_content += """
            </tbody>
        </table>
        
        <div class="footer">
            <p>Generated by WaybackMaster - Advanced Internet Archive Explorer</p>
        </div>
    </div>
</body>
</html>
    """
    
    # Write the HTML report
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logger.info(f"Batch report generated: {report_path}")
    
    # Try to open the report
    try:
        if sys.platform == 'win32':
            os.startfile(report_path)
        elif sys.platform == 'darwin':
            os.system(f'open "{report_path}"')
        else:
            os.system(f'xdg-open "{report_path}"')
    except Exception as e:
        logger.error(f"Could not open report: {e}")

# Manage file extensions
def manage_extensions(config):
    console.clear()
    display_banner()
    
    # Load current extensions
    default_extensions = load_extensions_from_file()
    
    console.print(Panel(
        "Manage file extensions to filter archive results.\n"
        "You can add, remove, or modify the list of extensions.",
        title="Extension Management",
        border_style="blue"
    ))
    
    # Display current extensions
    if default_extensions:
        ext_table = Table(title="Current Extensions")
        ext_table.add_column("Extension", style="cyan")
        ext_table.add_column("Example", style="green")
        
        for ext in sorted(default_extensions):
            ext_table.add_row(ext, f"example.{ext}")
        
        console.print(ext_table)
    else:
        console.print("[yellow]No extensions defined in extensions.txt[/]")
    
    # Extension management menu
    console.print(Panel(
        "1. [cyan]Add extensions[/]\n"
        "2. [cyan]Remove extensions[/]\n"
        "3. [cyan]Set common document extensions[/]\n"
        "4. [cyan]Set common media extensions[/]\n"
        "5. [cyan]Set common web extensions[/]\n"
        "6. [cyan]Set common archive extensions[/]\n"
        "7. [red]Return to main menu[/]",
        title="Options",
        border_style="blue"
    ))
    
    choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4", "5", "6", "7"], default="1")
    
    if choice == "1":
        # Add extensions
        new_exts = Prompt.ask("Enter extensions to add (comma-separated, without dots)")
        new_ext_list = [ext.strip().lower() for ext in new_exts.split(",") if ext.strip()]
        
        for ext in new_ext_list:
            if ext not in default_extensions and not ext.startswith('.'):
                default_extensions.append(ext)
        
        # Save to file
        with open(DEFAULT_EXTENSIONS_FILE, 'w') as f:
            for ext in sorted(default_extensions):
                f.write(f"{ext}\n")
        
        logger.info(f"Added {len(new_ext_list)} extensions to {DEFAULT_EXTENSIONS_FILE}")
    
    elif choice == "2":
        # Remove extensions
        if not default_extensions:
            console.print("[yellow]No extensions to remove.[/]")
        else:
            to_remove = Prompt.ask("Enter extensions to remove (comma-separated, without dots)")
            remove_list = [ext.strip().lower() for ext in to_remove.split(",") if ext.strip()]
            
            for ext in remove_list:
                if ext in default_extensions:
                    default_extensions.remove(ext)
            
            # Save to file
            with open(DEFAULT_EXTENSIONS_FILE, 'w') as f:
                for ext in sorted(default_extensions):
                    f.write(f"{ext}\n")
            
            logger.info(f"Removed {len(remove_list)} extensions from {DEFAULT_EXTENSIONS_FILE}")
    
    elif choice == "3":
        # Set common document extensions
        doc_extensions = ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "rtf", "odt", "ods", "odp"]
        
        if Confirm.ask(f"Replace current extensions with document extensions? ({', '.join(doc_extensions)})"):
            with open(DEFAULT_EXTENSIONS_FILE, 'w') as f:
                for ext in sorted(doc_extensions):
                    f.write(f"{ext}\n")
            
            logger.info(f"Set document extensions in {DEFAULT_EXTENSIONS_FILE}")
    
    elif choice == "4":
        # Set common media extensions
        media_extensions = ["jpg", "jpeg", "png", "gif", "bmp", "svg", "mp3", "mp4", "wav", "avi", "mov", "flv", "wmv"]
        
        if Confirm.ask(f"Replace current extensions with media extensions? ({', '.join(media_extensions)})"):
            with open(DEFAULT_EXTENSIONS_FILE, 'w') as f:
                for ext in sorted(media_extensions):
                    f.write(f"{ext}\n")
            
            logger.info(f"Set media extensions in {DEFAULT_EXTENSIONS_FILE}")
    
    elif choice == "5":
        # Set common web extensions
        web_extensions = ["html", "htm", "php", "asp", "aspx", "jsp", "cgi", "js", "css", "xml"]
        
        if Confirm.ask(f"Replace current extensions with web extensions? ({', '.join(web_extensions)})"):
            with open(DEFAULT_EXTENSIONS_FILE, 'w') as f:
                for ext in sorted(web_extensions):
                    f.write(f"{ext}\n")
            
            logger.info(f"Set web extensions in {DEFAULT_EXTENSIONS_FILE}")
    
    elif choice == "6":
        # Set common archive extensions
        archive_extensions = ["zip", "rar", "7z", "tar", "gz", "bz2", "iso", "dmg", "tgz"]
        
        if Confirm.ask(f"Replace current extensions with archive extensions? ({', '.join(archive_extensions)})"):
            with open(DEFAULT_EXTENSIONS_FILE, 'w') as f:
                for ext in sorted(archive_extensions):
                    f.write(f"{ext}\n")
            
            logger.info(f"Set archive extensions in {DEFAULT_EXTENSIONS_FILE}")
    
    else:  # Return to main menu
        return
    
    input("\nPress Enter to return to extensions menu...")
    manage_extensions(config)

# Settings menu
def settings_menu(config):
    console.clear()
    display_banner()
    
    console.print(Panel(
        "Configure application settings and preferences.",
        title="Settings",
        border_style="blue"
    ))
    
    # Show current settings
    settings_table = Table(title="Current Settings")
    settings_table.add_column("Setting", style="cyan")
    settings_table.add_column("Value", style="green")
    
    settings_table.add_row("Output Directory", config.get("output_directory", DEFAULT_OUTPUT_DIR))
    settings_table.add_row("Max Worker Threads", str(config.get("max_workers", MAX_WORKERS)))
    settings_table.add_row("API Rate Limit (seconds)", str(config.get("api_rate_limit", API_RATE_LIMIT)))
    settings_table.add_row("Check Wayback Snapshots", "Yes" if config.get("check_wayback_snapshots", True) else "No")
    settings_table.add_row("Download Files", "Yes" if config.get("download_files", False) else "No")
    
    console.print(settings_table)
    
    # Settings menu
    console.print(Panel(
        "1. [cyan]Change output directory[/]\n"
        "2. [cyan]Set max worker threads[/]\n"
        "3. [cyan]Set API rate limit[/]\n"
        "4. [cyan]Toggle wayback snapshot checking[/]\n"
        "5. [cyan]Toggle file downloading[/]\n"
        "6. [cyan]Reset to defaults[/]\n"
        "7. [red]Return to main menu[/]",
        title="Options",
        border_style="blue"
    ))
    
    choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4", "5", "6", "7"], default="7")
    
    if choice == "1":
        # Change output directory
        current_dir = config.get("output_directory", DEFAULT_OUTPUT_DIR)
        new_dir = Prompt.ask("Enter new output directory path", default=current_dir)
        
        if new_dir != current_dir:
            try:
                os.makedirs(new_dir, exist_ok=True)
                config["output_directory"] = new_dir
                save_config(config)
                logger.info(f"Output directory changed to: {new_dir}")
            except Exception as e:
                logger.error(f"Could not create directory: {e}")
    
    elif choice == "2":
        # Set max worker threads
        current_workers = config.get("max_workers", MAX_WORKERS)
        new_workers = Prompt.ask("Enter maximum number of worker threads (1-50)", default=str(current_workers))
        
        try:
            new_workers = int(new_workers)
            if 1 <= new_workers <= 50:
                config["max_workers"] = new_workers
                save_config(config)
                logger.info(f"Max worker threads set to: {new_workers}")
            else:
                logger.warning("Value must be between 1 and 50.")
        except ValueError:
            logger.warning("Please enter a valid number.")
    
    elif choice == "3":
        # Set API rate limit
        current_limit = config.get("api_rate_limit", API_RATE_LIMIT)
        new_limit = Prompt.ask("Enter API rate limit in seconds (1-30)", default=str(current_limit))
        
        try:
            new_limit = float(new_limit)
            if 1 <= new_limit <= 30:
                config["api_rate_limit"] = new_limit
                save_config(config)
                logger.info(f"API rate limit set to: {new_limit} seconds")
            else:
                logger.warning("Value must be between 1 and 30.")
        except ValueError:
            logger.warning("Please enter a valid number.")
    
    elif choice == "4":
        # Toggle wayback snapshot checking
        current = config.get("check_wayback_snapshots", True)
        config["check_wayback_snapshots"] = not current
        save_config(config)
        logger.info(f"Wayback snapshot checking: {'Enabled' if not current else 'Disabled'}")
    
    elif choice == "5":
        # Toggle file downloading
        current = config.get("download_files", False)
        config["download_files"] = not current
        save_config(config)
        logger.info(f"File downloading: {'Enabled' if not current else 'Disabled'}")
    
    elif choice == "6":
        # Reset to defaults
        if Confirm.ask("Reset all settings to defaults?", default=False):
            config = {
                "default_extensions": [],
                "output_directory": DEFAULT_OUTPUT_DIR,
                "max_workers": MAX_WORKERS,
                "api_rate_limit": API_RATE_LIMIT,
                "check_wayback_snapshots": True,
                "download_files": False,
                "recent_domains": config.get("recent_domains", [])
            }
            save_config(config)
            logger.info("Settings reset to defaults.")
    
    else:  # Return to main menu
        return
    
    input("\nPress Enter to return to settings menu...")
    settings_menu(config)

# Utility to select extensions for a scan
def select_extensions(config):
    # Load default extensions
    default_extensions = load_extensions_from_file()
    
    if default_extensions:
        console.print(Panel(
            f"Available extensions: {', '.join(default_extensions)}",
            title="File Extensions",
            border_style="blue"
        ))
        
        use_default = Confirm.ask("Use these extensions?", default=True)
        
        if use_default:
            return default_extensions
    
    # Custom extensions
    custom_exts = Prompt.ask("Enter file extensions to filter (comma-separated, without dots)")
    custom_ext_list = [ext.strip().lower() for ext in custom_exts.split(",") if ext.strip()]
    
    # Remove dots if present
    custom_ext_list = [ext[1:] if ext.startswith('.') else ext for ext in custom_ext_list]
    
    if not custom_ext_list:
        logger.warning("No extensions specified. Using all file types.")
        return []
    
    return custom_ext_list

# View results of previous scans
def view_results(config):
    console.clear()
    display_banner()
    
    output_dir = config.get("output_directory", DEFAULT_OUTPUT_DIR)
    
    if not os.path.exists(output_dir):
        console.print(f"[yellow]Output directory {output_dir} does not exist.[/]")
        input("\nPress Enter to return to main menu...")
        return
    
    # Get all subdirectories (domains)
    domains = []
    try:
        for item in os.listdir(output_dir):
            if os.path.isdir(os.path.join(output_dir, item)):
                domains.append(item)
    except Exception as e:
        logger.error(f"Error reading output directory: {e}")
    
    if not domains:
        console.print("[yellow]No scan results found.[/]")
        input("\nPress Enter to return to main menu...")
        return
    
    # Display domains
    domains_table = Table(title="Available Scan Results")
    domains_table.add_column("Domain", style="cyan")
    domains_table.add_column("Scan Date", style="green")
    domains_table.add_column("Files Found", style="yellow")
    
    for domain in sorted(domains):
        domain_dir = os.path.join(output_dir, domain)
        summary_path = os.path.join(domain_dir, f"{domain}_summary.json")
        
        scan_date = "Unknown"
        files_found = "N/A"
        
        if os.path.exists(summary_path):
            try:
                with open(summary_path, 'r') as f:
                    summary = json.load(f)
                    
                    # Format the date
                    if 'scan_date' in summary:
                        try:
                            date_obj = datetime.fromisoformat(summary['scan_date'])
                            scan_date = date_obj.strftime('%Y-%m-%d %H:%M')
                        except:
                            scan_date = summary['scan_date']
                    
                    # Get file count
                    if 'total_urls' in summary:
                        files_found = str(summary['total_urls'])
            except:
                pass
        
        domains_table.add_row(domain, scan_date, files_found)
    
    console.print(domains_table)
    
    # Options
    selected_domain = Prompt.ask(
        "Enter domain to view results (or 'back' to return to main menu)",
        default="back"
    )
    
    if selected_domain.lower() == 'back':
        return
    
    if selected_domain in domains:
        domain_dir = os.path.join(output_dir, selected_domain)
        report_path = os.path.join(domain_dir, f"{selected_domain}_report.html")
        
        if os.path.exists(report_path):
            try:
                # Open the report
                if sys.platform == 'win32':
                    os.startfile(report_path)
                elif sys.platform == 'darwin':
                    os.system(f'open "{report_path}"')
                else:
                    os.system(f'xdg-open "{report_path}"')
            except Exception as e:
                logger.error(f"Could not open report: {e}")
                
                # Fallback - show directory contents
                try:
                    if sys.platform == 'win32':
                        os.startfile(domain_dir)
                    elif sys.platform == 'darwin':
                        os.system(f'open "{domain_dir}"')
                    else:
                        os.system(f'xdg-open "{domain_dir}"')
                except:
                    pass
        else:
            console.print(f"[yellow]Report not found for {selected_domain}.[/]")
            
            # Show directory contents instead
            try:
                if sys.platform == 'win32':
                    os.startfile(domain_dir)
                elif sys.platform == 'darwin':
                    os.system(f'open "{domain_dir}"')
                else:
                    os.system(f'xdg-open "{domain_dir}"')
            except Exception as e:
                logger.error(f"Could not open directory: {e}")
    else:
        console.print(f"[red]Domain {selected_domain} not found in results.[/]")
    
    input("\nPress Enter to return to results menu...")
    view_results(config)

# Main program entry point
if __name__ == "__main__":
    try:
        # Ensure output directory exists
        config = load_config()
        os.makedirs(config.get("output_directory", DEFAULT_OUTPUT_DIR), exist_ok=True)
        
        # Run the main menu
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Program interrupted by user. Exiting...[/]")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        console.print(f"[red]An unexpected error occurred: {e}[/]")
        input("Press Enter to exit...")
        sys.exit(1)
