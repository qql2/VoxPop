#!/usr/bin/env python3
"""
知乎爬虫 — 搜索"程序员"相关话题，抓取问题和回答
使用 Playwright 浏览器自动化
输出到 PostgreSQL（zhihu_content + zhihu_comment 表）
"""

import asyncio, json, sys, re, time, os
from datetime import datetime
from urllib.parse import quote, urlencode

from playwright.async_api import async_playwright, Page, BrowserContext

DB_CONFIG = {
    "host": "127.0.0.1", "port": 5432, "user": "postgres",
    "password": "postgres", "database": "mindspider",
}

KEYWORDS = [
    "程序员 职业发展",
    "程序员 996",
    "前端开发",
    "AI 取代程序员",
    "程序员 薪资",
    "大模型 程序员",
    "35岁 程序员",
    "互联网裁员",
    "后端开发",
]

async def pg_connect():
    import asyncpg
    return await asyncpg.connect(**DB_CONFIG)

async def init_db(conn):
    """确保 zhihu_content 和 zhihu_comment 表存在（兼容 MindSpider 的 MySQL 结构改 PostgreSQL）"""
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS zhihu_content (
            id SERIAL PRIMARY KEY,
            content_id VARCHAR(255) UNIQUE,
            title TEXT,
            content TEXT,
            url TEXT,
            content_type VARCHAR(32),
            add_ts BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::bigint
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS zhihu_comment (
            id SERIAL PRIMARY KEY,
            content_id VARCHAR(255),
            content TEXT,
            add_ts BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::bigint
        )
    """)
    # Also create index
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_zhihu_comment_cid ON zhihu_comment(content_id)")

def ensure_url_has_answer(url: str) -> str:
    """确保问题 URL 带 answer 路由"""
    if "/answer/" in url:
        return url
    return url  # zhuanlan / question 直接返回

async def search_zhihu(page: Page, keyword: str, max_results: int = 5):
    """搜索知乎，返回结果 URL 列表"""
    search_url = f"https://www.zhihu.com/search?type=content&q={quote(keyword)}"
    print(f"  搜索: {keyword}")
    
    await page.goto(search_url, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(3000)
    
    # 等待搜索结果加载
    try:
        await page.wait_for_selector('[data-za-module="SearchResultItem"]', timeout=10000)
    except:
        try:
            await page.wait_for_selector('.Card', timeout=5000)
        except:
            print(f"    搜索页面加载失败，可能需登录")
            return []
    
    # 提取结果链接
    links = []
    items = await page.query_selector_all('[data-za-module="SearchResultItem"] a[href*="zhihu.com"]')
    
    for item in items[:max_results]:
        href = await item.get_attribute("href")
        if href and href not in links:
            if "/question/" in href or "/answer/" in href or "/zhuanlan/" in href:
                if not href.startswith("http"):
                    href = "https:" + href if href.startswith("//") else "https://www.zhihu.com" + href
                links.append(href)
    
    if not links:
        # 备选：从页面中提取所有链接
        all_links = await page.evaluate('''
            () => {
                const links = [];
                document.querySelectorAll('a[href*="/question/"], a[href*="/answer/"]').forEach(a => {
                    const h = a.href;
                    if (h && !links.includes(h) && !h.includes('search')) links.push(h);
                });
                return [...new Set(links)];
            }
        ''')
        links = all_links[:max_results]
    
    print(f"    找到 {len(links)} 个结果")
    return links

async def extract_content(page: Page, url: str) -> dict:
    """提取单个知乎内容（问题/文章/回答）"""
    print(f"  提取: {url[:80]}")
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"    加载失败: {e}")
        return None
    
    result = await page.evaluate('''
        () => {
            // 获取标题
            const titleEl = document.querySelector('h1.QuestionHeader-title') 
                         || document.querySelector('h1[data-za-extra-position]')
                         || document.querySelector('h1');
            const title = titleEl ? titleEl.textContent.trim() : '';
            
            // 获取正文内容
            const contentEl = document.querySelector('.RichText.ztext')
                           || document.querySelector('.Post-RichTextContainer .RichText')
                           || document.querySelector('article .RichText');
            const content = contentEl ? contentEl.textContent.trim().slice(0, 2000) : '';
            
            return { title, content, url: window.location.href };
        }
    ''')
    
    if not result.get('title') and not result.get('content'):
        print(f"    未提取到内容（可能需要登录）")
        return None
    
    return result

async def extract_comments(page: Page, url: str) -> list:
    """提取知乎评论"""
    print(f"  提取评论: {url[:60]}...")
    
    # 尝试点击展开评论
    try:
        # 寻找并点击"查看全部评论"按钮
        buttons = await page.query_selector_all('button:has-text("评论")')
        for btn in buttons:
            text = await btn.text_content()
            if text and ('查看' in text or '全部' in text or '条' in text):
                await btn.click()
                await page.wait_for_timeout(2000)
                break
    except:
        pass
    
    # 提取评论
    comments = await page.evaluate('''
        () => {
            const items = [];
            document.querySelectorAll('.CommentItem, .CommentItemV2').forEach(el => {
                const textEl = el.querySelector('.CommentContent, .RichText');
                if (textEl) {
                    const text = textEl.textContent.trim();
                    if (text) items.push(text.slice(0, 1000));
                }
            });
            return items;
        }
    ''')
    
    if not comments:
        # 备选：从评论区提取
        comments = await page.evaluate('''
            () => {
                const items = [];
                document.querySelectorAll('[data-za-module="CommentItem"]').forEach(el => {
                    const text = el.textContent.trim();
                    if (text && text.length > 5) items.push(text.slice(0, 1000));
                });
                return items;
            }
        ''')
    
    print(f"    提取 {len(comments)} 条评论")
    return comments[:30]  # 限制最多30条

async def crawl_keyword(page: Page, keyword: str, conn):
    """搜索 + 提取 + 入库，完整链路"""
    print(f"\n{'='*50}")
    print(f"关键词: {keyword}")
    
    urls = await search_zhihu(page, keyword, max_results=5)
    
    for url in urls:
        # 提取内容
        content = await extract_content(page, url)
        if not content:
            continue
        
        content_id = re.sub(r'[^a-zA-Z0-9]', '_', url.split('zhihu.com')[-1]).strip('_')
        
        # 写入 content 表
        try:
            await conn.execute("""
                INSERT INTO zhihu_content (content_id, title, content, url, content_type)
                VALUES ($1, $2, $3, $4, 'search')
                ON CONFLICT (content_id) DO NOTHING
            """, content_id, content.get('title',''), content.get('content',''), url)
        except Exception as e:
            print(f"    DB error (content): {e}")
        
        # 提取评论（需要重新加载评论页面）
        comments = await extract_comments(page, url)
        
        for comment_text in comments:
            try:
                await conn.execute("""
                    INSERT INTO zhihu_content (content_id, title, content, url, content_type)
                    VALUES ($1, $2, $3, $4, 'comment')
                    ON CONFLICT (content_id) DO NOTHING
                """, f"{content_id}_comment_{hash(comment_text) % 10000000}", 
                    f"评论:{content.get('title','')[:30]}", comment_text, url)
            except Exception as e:
                pass
        
        await page.wait_for_timeout(2000)  # 礼貌延迟

async def main():
    print("=== 知乎爬虫 — 全岗位态度盘点 ===")
    print(f"关键词: {', '.join(KEYWORDS)}")
    print("首次运行需要扫码登录知乎（浏览器窗口会弹出）\n")
    
    conn = await pg_connect()
    await init_db(conn)
    
    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800},
            locale='zh-CN',
        )
        page = await context.new_page()
        
        # 先打开知乎首页，触发登录检查
        print("打开知乎首页...")
        await page.goto("https://www.zhihu.com/signin", wait_until="networkidle", timeout=30000)
        
        # 检查是否需要登录
        is_logged_in = await page.evaluate('() => document.cookie.includes("z_c0")')
        if not is_logged_in:
            print("\n⚠️  需要扫码登录知乎")
            print("   浏览器窗口已打开 → 用知乎 App 扫码（或手机号登录）")
            print("   登录成功后按回车继续...")
            input("   [按回车继续] ")
            # 等待登录完成
            await page.wait_for_timeout(3000)
        
        # 检查登录状态
        page_url = page.url
        await page.goto("https://www.zhihu.com", wait_until="networkidle", timeout=30000)
        is_logged_in = await page.evaluate('() => document.cookie.includes("z_c0")')
        print(f"\n登录状态: {'✅ 已登录' if is_logged_in else '❌ 未登录（将以非登录模式抓取）'}")
        
        if not is_logged_in:
            print("非登录模式下可访问公开内容，但受限。继续尝试...")
        
        # 逐个关键词爬取
        for kw in KEYWORDS:
            try:
                await crawl_keyword(page, kw, conn)
            except Exception as e:
                print(f"  关键词 {kw} 出错: {e}")
                continue
        
        await browser.close()
    
    # 统计结果
    rows = await conn.fetch("SELECT COUNT(*) as cnt FROM zhihu_content")
    print(f"\n✅ 爬取完成！zhihu_content 共 {rows[0]['cnt']} 条")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
