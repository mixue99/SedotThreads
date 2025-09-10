import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
import aiohttp

async def grab_post_video(post_url: str, output_filename: str = "video_post.mp4"):
    video_url = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # headful biar bisa observasi
        page = await browser.new_page()

        # Tangkap semua response
        page.on("response", lambda resp: asyncio.create_task(capture_video_url(resp)))

        async def capture_video_url(resp):
            nonlocal video_url
            try:
                url = resp.url
                if ".mp4" in url and not video_url:
                    video_url = url
            except:
                pass

        await page.goto(post_url, timeout=60000)
        await page.wait_for_timeout(3000)

        # Coba klik tombol play kalau ada
        try:
            await page.locator("button").filter(has_text="Play").first.click()
            await page.wait_for_timeout(3000)
        except:
            pass

        # Tunggu video URL tertangkap
        for _ in range(10):
            if video_url:
                break
            await page.wait_for_timeout(1000)

        await browser.close()

    if not video_url:
        print("[!] Gagal menemukan video URL.")
        return

    print(f"[✓] Video URL ditemukan: {video_url}")
    await download_video(video_url, output_filename)

async def download_video(url: str, filename: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.read()
            Path(filename).write_bytes(data)
            print(f"[✓] Video disimpan → {filename}")

if __name__ == "__main__":
    post_url = "https://www.threads.com/@ggj95438/post/DOasHA4EcdU?xmt=AQF0JwnE5GN8idL1Fno6-G-2OUZwklXFkf1lGi_sP_Y9DA"
    output_name = "video_arnoldalvaro.mp4"
    asyncio.run(grab_post_video(post_url, output_name))
