#!/usr/bin/env python3
"""
Threads Video Downloader & Scraper v2.0
Enhanced version specifically designed for Threads.com
"""

import os
import re
import requests
import time
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright
from typing import List, Dict, Optional

class ThreadsDownloader:
    def __init__(self):
        self.output_dir = "downloads"
        self.urls_file = "scraped_urls.txt"
        self.input_file = "input.txt"
        self.log_file = f"threads_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        # Create directories
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Browser settings
        self.browser = None
        self.page = None
        
    def log(self, message: str, level: str = "INFO"):
        """Enhanced logging with file output"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}"
        print(log_message)
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_message + "\n")
    
    def init_browser(self):
        """Initialize browser session with Threads-optimized settings"""
        if not self.browser:
            self.log("Initializing browser for Threads...")
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=False,  # Set to True for headless mode
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                ]
            )
            
            context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            self.page = context.new_page()
            
            # Set additional headers
            self.page.set_extra_http_headers({
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            })
    
    def close_browser(self):
        """Close browser session"""
        if self.browser:
            self.browser.close()
            self.playwright.stop()
            self.browser = None
            self.page = None
    
    def extract_video_url_from_post(self, post_url: str) -> Optional[str]:
        """Extract video URL from Threads post using multiple strategies"""
        try:
            self.log(f"🔍 Analyzing Threads post: {post_url}")
            
            # Navigate to post
            self.page.goto(post_url, wait_until="networkidle", timeout=30000)
            self.log("✓ Page loaded, waiting for content...")
            
            # Wait longer for Threads content to load
            self.page.wait_for_timeout(8000)
            
            # Strategy 1: Look for video elements with multiple approaches
            video_selectors = [
                'video[src]',
                'video source[src]', 
                'video[data-src]',
                'div[role="img"] video',
                'article video',
                '[data-testid*="video"] video',
                'div[class*="video"] video',
                'video'
            ]
            
            for selector in video_selectors:
                try:
                    self.log(f"🔎 Trying selector: {selector}")
                    
                    # Check if elements exist
                    elements = self.page.locator(selector).all()
                    self.log(f"Found {len(elements)} elements with selector: {selector}")
                    
                    for i, element in enumerate(elements):
                        # Try multiple attributes
                        for attr in ['src', 'data-src', 'data-video-src', 'data-original']:
                            try:
                                video_src = element.get_attribute(attr)
                                if video_src and (video_src.startswith('http') or video_src.startswith('blob:')):
                                    self.log(f"✅ Found video URL via {selector}[{attr}]: {video_src[:100]}...")
                                    return video_src
                            except:
                                continue
                                
                except Exception as e:
                    self.log(f"Selector {selector} failed: {str(e)[:100]}", "DEBUG")
                    continue
            
            # Strategy 2: Check page source for video URLs
            self.log("🔎 Searching page source for video URLs...")
            content = self.page.content()
            
            # Look for video URL patterns in page source
            video_patterns = [
                r'https://[^"\']*\.mp4[^"\']*',
                r'https://[^"\']*video[^"\']*\.mp4',
                r'blob:https://[^"\']*',
                r'"video_url":"([^"]*)"',
                r'"src":"([^"]*\.mp4[^"]*)"'
            ]
            
            for pattern in video_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    for match in matches:
                        # Clean up the URL
                        if isinstance(match, tuple):
                            match = match[0]
                        match = match.replace('\\/', '/')
                        
                        if match.startswith(('http', 'blob:')):
                            self.log(f"✅ Found video URL in page source: {match[:100]}...")
                            return match
            
            # Strategy 3: Execute JavaScript to find video elements
            self.log("🔎 Using JavaScript to find video elements...")
            try:
                video_info = self.page.evaluate("""
                    () => {
                        const videos = document.querySelectorAll('video');
                        const results = [];
                        
                        videos.forEach((video, index) => {
                            const info = {
                                index: index,
                                src: video.src || video.getAttribute('data-src') || '',
                                currentSrc: video.currentSrc || '',
                                tagName: video.tagName,
                                attributes: {}
                            };
                            
                            // Get all attributes
                            for (let attr of video.attributes) {
                                info.attributes[attr.name] = attr.value;
                            }
                            
                            results.push(info);
                        });
                        
                        return results;
                    }
                """)
                
                self.log(f"JavaScript found {len(video_info)} video elements")
                
                for info in video_info:
                    self.log(f"Video {info['index']}: src='{info['src']}', currentSrc='{info['currentSrc']}'")
                    
                    # Check src attributes
                    for src_key in ['src', 'currentSrc']:
                        src = info.get(src_key, '')
                        if src and (src.startswith('http') or src.startswith('blob:')):
                            self.log(f"✅ Found video URL via JavaScript: {src}")
                            return src
                    
                    # Check attributes
                    for attr_name, attr_value in info.get('attributes', {}).items():
                        if 'src' in attr_name.lower() and attr_value:
                            if attr_value.startswith(('http', 'blob:')):
                                self.log(f"✅ Found video URL in attribute {attr_name}: {attr_value}")
                                return attr_value
                
            except Exception as e:
                self.log(f"JavaScript evaluation failed: {e}", "WARNING")
            
            # Strategy 4: Network request monitoring
            self.log("🔎 Monitoring network requests for video URLs...")
            video_urls = []
            
            def handle_response(response):
                url = response.url
                content_type = response.headers.get('content-type', '')
                
                if (url and 
                    (any(ext in url.lower() for ext in ['.mp4', '.webm', '.mov', 'video']) or
                     'video' in content_type.lower())):
                    video_urls.append(url)
                    self.log(f"📡 Network captured video URL: {url[:100]}...")
            
            # Set up response listener
            self.page.on("response", handle_response)
            
            # Trigger a refresh to capture network requests
            self.page.reload(wait_until="networkidle")
            self.page.wait_for_timeout(5000)
            
            if video_urls:
                return video_urls[0]  # Return first found video URL
            
            self.log("❌ No video URL found with any method", "WARNING")
            return None
                
        except Exception as e:
            self.log(f"❌ Error extracting video from {post_url}: {e}", "ERROR")
            return None
    
    def debug_page_structure(self, post_url: str):
        """Comprehensive debug analysis of Threads page"""
        try:
            self.log(f"🐛 DEBUG: Deep analysis of {post_url}")
            self.page.goto(post_url, wait_until="networkidle", timeout=30000)
            self.page.wait_for_timeout(5000)
            
            # Basic page info
            title = self.page.title()
            url = self.page.url
            self.log(f"📄 Page title: {title}")
            self.log(f"🔗 Final URL: {url}")
            
            # Check for common elements
            selectors_info = {
                'video': 'Video elements',
                'source': 'Source elements', 
                'img': 'Image elements',
                'div[role="img"]': 'Image role divs',
                'article': 'Article elements',
                '[data-testid]': 'Test ID elements',
                '[class*="video" i]': 'Video class elements',
                '[data-src]': 'Data-src elements'
            }
            
            for selector, description in selectors_info.items():
                try:
                    count = self.page.locator(selector).count()
                    self.log(f"🔍 {description}: {count} found")
                    
                    if count > 0 and count <= 5:  # Avoid spam for too many elements
                        elements = self.page.locator(selector).all()[:3]  # Check first 3
                        for i, element in enumerate(elements):
                            try:
                                tag = element.evaluate('el => el.tagName')
                                attrs = element.evaluate('''el => {
                                    const result = {};
                                    for (let attr of el.attributes) {
                                        if (attr.value.length < 150) {
                                            result[attr.name] = attr.value;
                                        }
                                    }
                                    return result;
                                }''')
                                
                                self.log(f"  Element {i+1} ({tag}): {attrs}")
                            except:
                                continue
                except:
                    continue
            
            # Search page source for video indicators
            content = self.page.content()
            indicators = [
                ('video', content.lower().count('video')),
                ('.mp4', content.count('.mp4')),
                ('blob:', content.count('blob:')),
                ('src=', content.count('src=')),
                ('data-src', content.count('data-src'))
            ]
            
            self.log("📋 Page source analysis:")
            for indicator, count in indicators:
                if count > 0:
                    self.log(f"  '{indicator}': {count} occurrences")
            
            # Try to capture all video-like URLs from source
            video_patterns = [
                r'https://[^"\'>\s]*\.mp4[^"\'>\s]*',
                r'blob:https://[^"\'>\s]*',
                r'"[^"]*video[^"]*"',
                r'src="([^"]*)"'
            ]
            
            self.log("🎯 Potential video URLs found in source:")
            for pattern in video_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                unique_matches = list(set(matches))[:5]  # Show max 5 unique matches
                
                for match in unique_matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    if len(match) > 20 and ('video' in match.lower() or '.mp4' in match.lower()):
                        self.log(f"  🎥 {match[:150]}...")
                        
        except Exception as e:
            self.log(f"❌ Debug analysis failed: {e}", "ERROR")
    
    def download_video(self, post_url: str) -> bool:
        """Download video from Threads post URL"""
        try:
            # Extract post ID for filename
            post_id_match = re.search(r'/post/([^/?]+)', post_url)
            post_id = post_id_match.group(1) if post_id_match else f"threads_{int(time.time())}"
            filename = f"threads_{post_id}.mp4"
            filepath = os.path.join(self.output_dir, filename)
            
            # Skip if already exists
            if os.path.exists(filepath):
                self.log(f"⏭️ File already exists: {filename}")
                return True
            
            # Get video URL
            video_url = self.extract_video_url_from_post(post_url)
            if not video_url:
                self.log(f"❌ No video URL found for: {post_url}", "ERROR")
                return False
            
            # Download video
            self.log(f"⬇️ Downloading: {filename}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.threads.net/',
                'Accept': '*/*'
            }
            
            response = requests.get(video_url, stream=True, headers=headers, timeout=60)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            if downloaded_size % (1024 * 1024) == 0:  # Log every MB
                                self.log(f"📥 Progress: {progress:.1f}% ({downloaded_size/1024/1024:.1f}MB)")
            
            file_size = os.path.getsize(filepath) / (1024 * 1024)  # MB
            self.log(f"✅ Downloaded: {filepath} ({file_size:.1f}MB)")
            return True
            
        except Exception as e:
            self.log(f"❌ Error downloading {post_url}: {e}", "ERROR")
            return False
    
    def scrape_profile_videos(self, profile_url: str) -> List[str]:
        """Scrape video URLs from Threads profile"""
        self.log(f"🔍 Starting profile scrape: {profile_url}")
        self.init_browser()
        
        video_urls = []
        
        try:
            # Navigate to profile
            self.page.goto(profile_url, wait_until="networkidle", timeout=30000)
            self.page.wait_for_timeout(5000)
            
            # Scroll to load more posts
            self.log("📜 Scrolling to load posts...")
            for i in range(15):  # More scrolls for better coverage
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self.page.wait_for_timeout(2000)
                if i % 5 == 0:
                    self.log(f"Scroll {i+1}/15 completed")
            
            # Find post links
            self.log("🔎 Searching for post links...")
            
            # Multiple strategies to find post links
            post_links = set()
            
            # Strategy 1: Direct post links
            links = self.page.locator('a[href*="/post/"]').all()
            for link in links:
                href = link.get_attribute('href')
                if href:
                    if href.startswith('/'):
                        href = f"https://www.threads.net{href}"
                    post_links.add(href)
            
            # Strategy 2: JavaScript extraction
            try:
                js_links = self.page.evaluate("""
                    () => {
                        const links = [];
                        document.querySelectorAll('a').forEach(a => {
                            if (a.href && a.href.includes('/post/')) {
                                links.push(a.href);
                            }
                        });
                        return [...new Set(links)];
                    }
                """)
                post_links.update(js_links)
            except:
                pass
            
            post_links = list(post_links)
            self.log(f"📋 Found {len(post_links)} potential posts")
            
            # Check each post for videos
            for i, post_link in enumerate(post_links[:20], 1):  # Limit to first 20 posts
                self.log(f"🔍 Checking post {i}: {post_link}")
                
                try:
                    video_url = self.extract_video_url_from_post(post_link)
                    if video_url:
                        self.log(f"✅ Video found in post {i}")
                        video_urls.append(post_link)
                    else:
                        self.log(f"❌ No video in post {i}")
                        
                except Exception as e:
                    self.log(f"⚠️ Error checking post {i}: {e}", "WARNING")
                
                # Rate limiting
                time.sleep(3)
            
            # Save results
            if video_urls:
                with open(self.urls_file, 'w', encoding='utf-8') as f:
                    for url in video_urls:
                        f.write(url + '\n')
                
                self.log(f"✅ Profile scraping completed! Found {len(video_urls)} videos")
                self.log(f"📄 URLs saved to: {self.urls_file}")
            else:
                self.log("❌ No videos found in profile", "WARNING")
                
        except Exception as e:
            self.log(f"❌ Error during profile scraping: {e}", "ERROR")
        
        finally:
            self.close_browser()
        
        return video_urls
    
    def batch_download(self) -> None:
        """Download videos from input.txt"""
        if not os.path.exists(self.input_file):
            self.log(f"❌ Input file not found: {self.input_file}", "ERROR")
            return
        
        with open(self.input_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
        
        if not urls:
            self.log("❌ No URLs found in input file", "ERROR")
            return
        
        self.log(f"🚀 Starting batch download of {len(urls)} videos...")
        self.init_browser()
        
        success_count = 0
        for i, url in enumerate(urls, 1):
            self.log(f"📥 Processing {i}/{len(urls)}: {url}")
            
            if self.download_video(url):
                success_count += 1
            
            # Rate limiting between downloads
            time.sleep(3)
        
        self.close_browser()
        self.log(f"✅ Batch download completed! {success_count}/{len(urls)} successful")
    
    def run(self):
        """Main application"""
        print("=" * 70)
        print("🎬 THREADS VIDEO DOWNLOADER & SCRAPER v2.0")
        print("=" * 70)
        print()
        print("Choose an option:")
        print("1. 🔍 Scrape video URLs from Threads profile")
        print("2. ⬇️  Download videos from input.txt")
        print("3. 🐛 Debug single post (analyze structure)")
        print("4. 🧪 Test single video download")
        print("5. ❌ Exit")
        print()
        
        while True:
            choice = input("Enter your choice (1-5): ").strip()
            
            if choice == "1":
                print("\n" + "="*50)
                print("🔍 PROFILE SCRAPING MODE")
                print("="*50)
                
                profile_url = input("\nEnter Threads profile URL: ").strip()
                
                if not profile_url or 'threads.com/@' not in profile_url:
                    print("❌ Invalid URL! Use: https://www.threads.com/@username")
                    continue
                
                print(f"\n🚀 Scraping: {profile_url}")
                video_urls = self.scrape_profile_videos(profile_url)
                
                if video_urls:
                    print(f"\n✅ Found {len(video_urls)} video posts!")
                    print(f"📄 Saved to: {self.urls_file}")
                else:
                    print("\n❌ No videos found")
                break
                
            elif choice == "2":
                print("\n" + "="*50)
                print("⬇️ BATCH DOWNLOAD MODE")
                print("="*50)
                
                if not os.path.exists(self.input_file):
                    print(f"❌ File '{self.input_file}' not found!")
                    print(f"Create it with video URLs (one per line)")
                    continue
                
                print(f"\n🚀 Downloading from: {self.input_file}")
                self.batch_download()
                break
                
            elif choice == "3":
                print("\n" + "="*50)
                print("🐛 DEBUG MODE")
                print("="*50)
                
                post_url = input("\nEnter Threads post URL: ").strip()
                
                if not post_url or 'threads.com' not in post_url:
                    print("❌ Invalid URL!")
                    continue
                
                print(f"\n🔍 Debugging: {post_url}")
                self.init_browser()
                self.debug_page_structure(post_url)
                self.close_browser()
                print(f"\n📄 Check log file: {self.log_file}")
                break
                
            elif choice == "4":
                print("\n" + "="*50)
                print("🧪 SINGLE VIDEO TEST")
                print("="*50)
                
                post_url = input("\nEnter Threads post URL: ").strip()
                
                if not post_url or 'threads.com' not in post_url:
                    print("❌ Invalid URL!")
                    continue
                
                print(f"\n🧪 Testing: {post_url}")
                self.init_browser()
                success = self.download_video(post_url)
                self.close_browser()
                
                if success:
                    print(f"\n✅ Test successful! Check {self.output_dir}/")
                else:
                    print(f"\n❌ Test failed. Check log: {self.log_file}")
                break
                
            elif choice == "5":
                print("\n👋 Goodbye!")
                break
                
            else:
                print("❌ Invalid choice! Enter 1-5.")

def main():
    try:
        downloader = ThreadsDownloader()
        downloader.run()
    except KeyboardInterrupt:
        print("\n\n⏹️ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()