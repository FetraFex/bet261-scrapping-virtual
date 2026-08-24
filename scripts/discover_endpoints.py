import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.settings import settings

async def discover_page(page, url, name, results_dict):
    print(f"\n--- Discovering {name}: {url} ---")
    requests_found = []

    # Intercept network requests
    page.on("request", lambda request: process_request(request, requests_found))
    page.on("response", lambda response: asyncio.create_task(process_response(response, requests_found)))

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        # Wait a bit longer for dynamic content
        await page.wait_for_timeout(5000)
    except Exception as e:
        print(f"Error loading {name}: {e}")

    results_dict[name] = requests_found

def process_request(request, requests_found):
    resource_type = request.resource_type
    if resource_type in ["fetch", "xhr"]:
        print(f"Detected request: {request.method} {request.url}")

async def process_response(response, requests_found):
    request = response.request
    resource_type = request.resource_type
    if resource_type in ["fetch", "xhr"]:
        try:
            content_type = response.headers.get("content-type", "")
            data = {
                "url": request.url,
                "method": request.method,
                "status": response.status,
                "content_type": content_type,
                "headers": dict(request.headers)
            }
            
            if "application/json" in content_type:
                try:
                    json_data = await response.json()
                    # Only store a snippet to avoid huge files, or structure if it's large
                    if isinstance(json_data, dict):
                        data["sample_keys"] = list(json_data.keys())
                        data["sample_snippet"] = str(json_data)[:500]
                    elif isinstance(json_data, list):
                        data["is_list"] = True
                        data["list_length"] = len(json_data)
                        if len(json_data) > 0:
                            data["sample_snippet"] = str(json_data[0])[:500]
                except Exception:
                    data["sample_snippet"] = "Could not parse JSON"
            
            requests_found.append(data)
        except Exception as e:
            pass # some responses might be aborted or body unavailable

async def main():
    results = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.BROWSER_HEADLESS)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        
        await discover_page(page, settings.MATCHES_URL, "MATCHES", results)
        await discover_page(page, settings.RESULTS_URL, "RESULTS", results)
        await discover_page(page, settings.RANKING_URL, "RANKING", results)

        await browser.close()

    output_file = Path("discovery_report.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\nDiscovery complete. Report saved to {output_file.absolute()}")

if __name__ == "__main__":
    asyncio.run(main())
