Sedot@Threads v.1  
_Scraping video @Threads unlimited_


## ✨ Fitur
- 📜 **Scrape** semua URL video dari profil/post Threads
- 📥 **Download** semua video dari file `.txt`
- ⚡ **Grab** (scrape + download langsung)
- 🔄 Unlimited scroll untuk ambil semua video
- 📊 Progress bar & logging rapi

---

## 📦 Instalasi
```bash
git clone https://github.com/Yoyok/sedotthreads.git
cd sedotthreads/sedotthreads
pip install -r requirements.txt
playwright install chromium

## 🚀 Cara Pakai
python threads_tool.py scrape --target-url https://www.threads.net/@username
python threads_tool.py download --input-file video_urls.txt
python threads_tool.py grab --target-url https://www.threads.net/@username

