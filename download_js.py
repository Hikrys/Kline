import asyncio
import aiohttp
import os
import sys


async def download_chart_library():
    url = "https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"
    proxy = "http://127.0.0.1:10809"  # 用你的万能代理！
    save_path = os.path.join("static", "lightweight-charts.standalone.production.js")

    # 确保static目录存在，避免文件写入失败
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    print(f"🚀 正在通过代理 {proxy} 强行下载前端图表库...")

    try:
        # 增加SSL验证关闭+超时配置，解决常见连接问题
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, proxy=proxy, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(text)
                    print(f"✅ 下载成功！文件已保存到: {save_path}")
                else:
                    print(f"❌ 下载失败，状态码: {resp.status}")
                    # 尝试不使用代理重试
                    print("🔄 尝试不使用代理重新下载...")
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp_retry:
                        if resp_retry.status == 200:
                            text = await resp_retry.text()
                            with open(save_path, "w", encoding="utf-8") as f:
                                f.write(text)
                            print(f"✅ 无代理下载成功！文件已保存到: {save_path}")
                        else:
                            print(f"❌ 无代理下载也失败，状态码: {resp_retry.status}")
    except Exception as e:
        print(f"❌ 代理下载出错: {e}")
        # 代理失败时，自动尝试无代理下载
        try:
            print("🔄 尝试不使用代理重新下载...")
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        with open(save_path, "w", encoding="utf-8") as f:
                            f.write(text)
                        print(f"✅ 无代理下载成功！文件已保存到: {save_path}")
                    else:
                        print(f"❌ 无代理下载失败，状态码: {resp.status}")
                        # 提供国内镜像源备选方案
                        print("🔄 尝试使用国内镜像源下载...")
                        mirror_url = "https://cdn.jsdelivr.net/npm/lightweight-charts/dist/lightweight-charts.standalone.production.js"
                        async with session.get(mirror_url, timeout=aiohttp.ClientTimeout(total=30)) as mirror_resp:
                            if mirror_resp.status == 200:
                                text = await mirror_resp.text()
                                with open(save_path, "w", encoding="utf-8") as f:
                                    f.write(text)
                                print(f"✅ 国内镜像源下载成功！文件已保存到: {save_path}")
                            else:
                                print(f"❌ 所有下载方式均失败，镜像源状态码: {mirror_resp.status}")
        except Exception as e2:
            print(f"❌ 无代理下载也失败: {e2}")
            print("💡 建议检查：1.代理是否运行 2.网络是否正常 3.替换为国内镜像源")


if __name__ == "__main__":
    # 移除弃用的事件循环配置，解决DeprecationWarning警告
    # 现代Python Windows版本无需手动设置事件循环策略
    asyncio.run(download_chart_library())