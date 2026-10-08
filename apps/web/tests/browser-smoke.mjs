// Run against tests/smoke_server.py and a frontend using API_UPSTREAM_URL.
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";
const modulePath = process.env.PLAYWRIGHT_MODULE;
const { chromium } = await import(modulePath ? pathToFileURL(path.join(modulePath, "index.mjs")).href : "playwright");
const base = process.env.SMOKE_WEB_URL || "http://127.0.0.1:18080";

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 1000 }, deviceScaleFactor: 1, colorScheme: "light" });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(base + "/textbook/1/chapter/1");
    await page.getByText("已保存的字幕", { exact: true }).waitFor();
    assert(await page.getByText("测试选择题", { exact: false }).isVisible());
    await page.reload();
    await page.getByText("已保存的字幕", { exact: true }).waitFor();

    // Locate the painted blue concept; clicking verifies the hidden hit canvas.
    await page.locator("canvas").first().waitFor();
    await page.locator("canvas").first().scrollIntoViewIfNeeded();
    await page.waitForTimeout(1200);
    await page.waitForFunction(() => {
      const canvas = document.querySelector("canvas");
      const data = canvas?.getContext("2d")?.getImageData(0, 0, canvas.width, canvas.height).data;
      return data && data.some((value, i) => i % 4 === 0 && value === 59 && data[i + 1] === 130 && data[i + 2] === 246);
    });
    const point = await page.evaluate(() => {
      const canvas = document.querySelector("canvas");
      const { data } = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height);
      const xs = [], ys = [];
      for (let i = 0; i < data.length; i += 4) {
        if (data[i] === 59 && data[i + 1] === 130 && data[i + 2] === 246) {
          xs.push((i / 4) % canvas.width);
          ys.push(Math.floor(i / 4 / canvas.width));
        }
      }
      const rect = canvas.getBoundingClientRect();
      return {
        x: rect.left + (Math.min(...xs) + Math.max(...xs)) / 2 * rect.width / canvas.width,
        y: rect.top + (Math.min(...ys) + Math.max(...ys)) / 2 * rect.height / canvas.height,
      };
    });
    await page.mouse.click(point.x, point.y);
    await page.getByText("关联概念：", { exact: true }).waitFor();
    assert(await page.getByRole("button", { name: "测试方法", exact: true }).isVisible());
    console.log("PASS graph click and related concept panel");

    await page.getByRole("link", { name: /2\.第二章/ }).click();
    await page.getByRole("heading", { name: "第二章", exact: true }).waitFor();
    assert.equal(await page.getByText("已保存的字幕", { exact: true }).count(), 0);
    assert(await page.getByRole("button", { name: "生成练习题", exact: true }).isVisible());
    await page.getByRole("link", { name: /1\.第一章/ }).click();
    await page.getByText("已保存的字幕", { exact: true }).waitFor();
    console.log("PASS subtitle restoration and chapter state isolation");

    await page.getByRole("button", { name: "标记本章已读完", exact: true }).click();
    await page.getByRole("button", { name: "已读完 · 撤销标记", exact: true }).waitFor();
    await page.locator('input[name="quiz-q-0"]').nth(1).check();
    await page.getByText("作答已保存", { exact: true }).waitFor();
    await page.reload();
    await page.getByRole("button", { name: "已读完 · 撤销标记", exact: true }).waitFor();
    assert(await page.locator('input[name="quiz-q-0"]').nth(1).isChecked());
    await page.getByRole("button", { name: "提交 (1/1)", exact: true }).click();
    await page.getByText("得分: 0 / 1", { exact: true }).waitFor();
    await page.reload();
    await page.getByText("得分: 0 / 1", { exact: true }).waitFor();
    await page.getByRole("link", { name: /打开课本错题本/ }).click();
    await page.getByRole("heading", { name: "课本错题本", exact: true }).waitFor();
    await page.locator('input[type="radio"]').first().check();
    await page.getByRole("button", { name: "检查并保存复习结果", exact: true }).click();
    await page.getByText("回答正确，已记录本次复习。", { exact: true }).waitFor();
    await page.reload();
    await page.getByText(/已复习 · 复习 1 次/).waitFor();
    await page.goto(base + "/textbook/1/chapter/1");
    await page.getByText("得分: 0 / 1", { exact: true }).waitFor();
    console.log("PASS read marker, draft, score and wrong-answer review persistence");

    await page.getByPlaceholder("针对本章内容提问...").fill("跨章检索概念是什么？");
    await page.getByRole("button", { name: "提问", exact: true }).click();
    await page.getByText("第二章 · PDF 第 3 页（文件页序）", { exact: true }).click();
    await page.getByRole("link", { name: "查看原文位置", exact: true }).first().click();
    await page.getByRole("link", { name: "打开原始教材第 3 页", exact: true }).waitFor();
    assert(await page.getByText("跨章检索概念是本章独有的定义。", { exact: true }).isVisible());
    await page.goto(base + "/textbook/1/chapter/1");
    await page.getByText("得分: 0 / 1", { exact: true }).waitFor();
    console.log("PASS same-textbook retrieval and source-page navigation");

    await page.getByRole("button", { name: "重新生成", exact: true }).first().click();
    await page.getByRole("button", { name: "简洁概述", exact: true }).click();
    await page.getByRole("button", { name: "生成讲解内容", exact: true }).click();
    await page.getByText("风格：concise；难度：medium", { exact: true }).first().waitFor();
    await page.getByText("整章末尾知识", { exact: true }).waitFor();
    await page.getByText(/原文 7208 字符 · 共 2 部分/).waitFor();
    assert.equal(await page.getByText("已保存的字幕", { exact: true }).count(), 0);
    assert(await page.getByRole("button", { name: "生成练习题", exact: true }).isVisible());
    assert(await page.getByRole("button", { name: "生成知识图谱", exact: true }).isVisible());
    assert(await page.getByRole("button", { name: "生成语音讲解", exact: true }).isVisible());
    await page.reload();
    await page.getByText("风格：concise；难度：medium", { exact: true }).first().waitFor();
    assert(await page.getByRole("button", { name: "生成语音讲解", exact: true }).isVisible());
    console.log("PASS style selection, regeneration and persistent invalidation");

    await page.getByRole("link", { name: "智能课本助手", exact: false }).first().click();
    await page.locator('input[type="file"]').setInputFiles({ name: "oversized.pdf", mimeType: "application/pdf", buffer: Buffer.alloc(1024 * 1024 + 1) });
    await page.getByText("文件大小不能超过 1 MB", { exact: true }).waitFor();
    console.log("PASS upload limit error through runtime proxy");
    assert.deepEqual(errors, []);
    console.log("PASS no uncaught browser errors");
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
