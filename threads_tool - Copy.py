#!/usr/bin/env python3
r"""
  ____           _       _     @Threads Unlimited
 / ___| ___   __| | ___ | |_   ___  _ __  ___
 \___ \| _ \ / _` |/ _ \| __| / _ \| '_ \/ __|
  ___) |  __/ (_| | (_) | |_ | (_) | | | \__ \
 |____/ \___|\__,_|\___/ \__(_)___/|_| |_|___/

        Sedot@Threads v.1  —  Scraping video @Threads unlimited
"""

import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from playwright.async_api import async_playwright

# === Setup logging ke file ===
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

class Tee:
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()

log_fh = open(log_file, "w", encoding="utf-8")
sys.stdout = Tee(sys.stdout, log_fh)
sys.stderr = Tee(sys.stderr, log_fh)

print(f"[LOG] Semua output disimpan di {log_file}")

# === CLI setup ===
app = typer.Typer(help="Scrape & download Threads videos (threads.net & threads.com).")
console = Console()

OUTPUT_DIR = Path("downloads")
OUTPUT_DIR.mkdir(exist_ok=True)

# Regex patterns
RE_CDN_IG = re.compile(r"https://(?:scontent|video)\.cdninstagram\.com/[^\"'\\\s]+", re.IGNORECASE)
RE_GENERIC_MP4 = re.compile(r"https?://[^\s\"']+\.mp4(?:\?[^\s\"']+)?", re.IGNORECASE)
RE_VIDEO_TAG = re.compile(r"<video[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
RE_SOURCE_TAG = re.compile(r"<source[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)

def normalize_urls(urls):
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

async def extract_urls_from_html(html: str):
    candidates = []
    candidates += RE_CDN_IG.findall(html)
    candidates += RE_GENERIC_MP4.findall(html)
    candidates += RE_VIDEO_TAG.findall(html)
    candidates += RE_SOURCE_TAG.findall(html)
    candidates = [u for u in candidates if "analytics" not in u and "metric" not in u]
    return normalize_urls(candidates)

async def scroll_to_bottom(page, max_rounds: int, wait_ms: int):
    prev_height = 0
    for _ in range(max_rounds):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(wait_ms)
        height = await page.evaluate("document.body.scrollHeight")
        if height == prev_height:
            break
        prev_height = height

async def scrape_with_playwright(
    target_url: str,
    headful: bool = False,
    scroll_max: int = 12,
    wait_ms: int = 2000,
    debug: bool = False
) -> list:
    parsed = urlparse(target_url)
    domain = parsed.hostname or ""
    mode = "threads.net" if "threads.net" in domain else "threads.com" if "threads.com" in domain else "generic"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headful)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
        )
        page = await context.new_page()

        console.log(f"[cyan]Opening target:[/cyan] {target_url}")
        await page.goto(target_url, timeout=90000, wait_until="load")
        await page.wait_for_timeout(2500)

        await scroll_to_bottom(page, max_rounds=scroll_max, wait_ms=wait_ms)

        harvested = []
        def on_response(resp):
            try:
                url = resp.url
                if RE_CDN_IG.search(url) or RE_GENERIC_MP4.search(url):
                    harvested.append(url)
            except Exception:
                pass
        page.on("response", on_response)

        html = await page.content()

        if debug:
            Path("debug_page.html").write_text(html, encoding="utf-8")
            console.log("[blue]Debug mode:[/blue] HTML saved to debug_page.html")

        await browser.close()

    html_urls = await extract_urls_from_html(html)
    all_urls = normalize_urls(harvested + html_urls)

    if mode == "threads.net":
        ig_first = [u for u in all_urls if "cdninstagram.com" in u]
        others = [u for u in all_urls if "cdninstagram.com" not in u]
        all_urls = ig_first + others

    return all_urls

async def save_urls_to_file(urls: list, output_file: Path):
    output_file.write_text("\n".join(urls), encoding="utf-8")
    console.log(f"[green]Saved {len(urls)} URLs → {output_file}[/green]")

async def download_one(session: aiohttp.ClientSession, url: str, dest: Path):
    try:
        async with session.get(url, timeout=120) as resp:
            resp.raise_for_status()
            with dest.open("wb") as f:
                async for chunk in resp.content.iter_chunked(256 * 1024):
                    if chunk:
                        f.write(chunk)
        return True
    except Exception as e:
        console.log(f"[red]Failed:[/red] {url} → {e}")
        return False

async def download_many(urls: list):
    urls = [u for u in urls if ".mp4" in u.lower()]
    if not urls:
        console.print("[yellow]Tidak ada URL video (.mp4) yang valid untuk diunduh.[/yellow]")
        return
    OUTPUT_DIR.mkdir(exist_ok=True)
    async with aiohttp.ClientSession() as session:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Downloading videos...", total=len(urls))
            idx = 0
            for url in urls:
                idx += 1
                filename = f"video_{idx}.mp4"
                dest = OUTPUT_DIR / filename
                ok = await download_one(session, url, dest)
                if ok:
                    progress.update(task, advance=1)

def validate_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme.startswith("http"):
        return ""
    return url

@app.command()
def download(
    input_file: Path = typer.Argument(None, help="File URL list"),
    input_file_opt: Path = typer.Option(None, "--input-file", help="File URL list (option)"),
):
    file_path = input_file_opt or input_file
    if not file_path or not file_path.exists():
        console.print("[red]Error:[/red] File input tidak ditemukan.")
        raise typer.Exit(code=1)

    urls = [
        u.strip()
        for u in file_path.read_text(encoding="utf-8").splitlines()
        if u.strip()
    ]
    if not urls:
        console.print("[yellow]Tidak ada URL di file input.[/yellow]")
        raise typer.Exit(code=0)

    asyncio.run(download_many(urls))


@app.command()
def grab(
    target_url: str = typer.Argument(None, help="Target URL"),
    target_url_opt: str = typer.Option(None, "--target-url", help="Target URL (option)"),
    headful: bool = typer.Option(False, "--headful", help="Show browser"),
    debug: bool = typer.Option(False, "--debug", help="Save HTML"),
    scroll_max: int = typer.Option(12, "--scroll-max", help="Max scroll rounds"),
    wait_ms: int = typer.Option(2000, "--wait-ms", help="Delay per scroll (ms)"),
):
    url = validate_url(target_url_opt or target_url)
    if not url:
        console.print("[red]Error:[/red] Harap masukkan URL target yang valid.")
        raise typer.Exit(code=1)

    urls = asyncio.run(
        scrape_with_playwright(url, headful=headful, scroll_max=scroll_max, wait_ms=wait_ms, debug=debug)
    )
    if not urls:
        console.print(f"[yellow]Tidak ditemukan video di {url}[/yellow]")
        raise typer.Exit(code=0)

    console.log(f"[yellow]Found {len(urls)} videos. Starting download...[/yellow]")
    asyncio.run(download_many(urls))


if __name__ == "__main__":
    app()
