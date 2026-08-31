async (page) => {
  await page.goto("http://127.0.0.1:8765/");
  await page.keyboard.press("Tab");
  const brief = page.getByLabel("Procurement brief");
  if (!(await brief.evaluate((element) => element === document.activeElement))) {
    throw new Error("brief did not receive keyboard focus");
  }
  await brief.fill("Buy two keyboards <script>window.ordersealInjected=true</script>");
  await page.getByLabel("Demonstrate post-commit acknowledgement loss").check();
  await page.getByRole("button", { name: "Build evidence-backed review" }).click();
  if (!(await page.evaluate(() => window.ordersealInjected === undefined))) {
    throw new Error("untrusted brief executed as script");
  }
  await page.getByRole("button", { name: "Confirm exact synthetic order" }).click();
  await page.getByRole("heading", { name: "Confirmation status unknown" }).waitFor();
  if (!(await page.getByRole("status").innerText()).includes("Do not submit again")) {
    throw new Error("ACK_UNKNOWN live status missing");
  }
  await page.keyboard.press("Tab");
  const checkStatus = page.getByRole("button", { name: "Check authoritative status" });
  if (!(await checkStatus.evaluate((element) => element === document.activeElement))) {
    throw new Error("status check did not receive keyboard focus");
  }
  await page.keyboard.press("Enter");
  await page.getByRole("heading", { name: "Verified synthetic order" }).waitFor();
  if (!(await page.getByRole("status").innerText()).includes("ACK_UNKNOWN reconciled")) {
    throw new Error("authoritative recovery status missing");
  }
}
