// 这段脚本放在后置操作：检查真实响应，不修改服务端数据。
pm.test("岗位列表返回 200", function () {
    pm.expect(pm.response.code).to.eql(200);
});
pm.test("响应类型是 JSON", function () {
    const contentType = pm.response.headers.get("Content-Type") || "";
    pm.expect(contentType.toLowerCase().includes("application/json")).to.eql(true);
});
pm.test("响应包含合法的 total 和 items", function () {
    const data = pm.response.json();
    pm.expect(data !== null && typeof data === "object" && !Array.isArray(data)).to.eql(true);
    pm.expect(Number.isInteger(data.total) && data.total >= 0).to.eql(true);
    pm.expect(Array.isArray(data.items)).to.eql(true);
});
pm.test("total 与岗位数组长度一致", function () {
    const data = pm.response.json();
    // 不固定为 11：合法的数据变化不应让契约测试失败。
    pm.expect(data.total).to.eql(data.items.length);
});
pm.test("岗位字段完整且符合基本规则", function () {
    const data = pm.response.json();
    pm.expect(Array.isArray(data.items)).to.eql(true);
    data.items.forEach(function (job) {
        pm.expect(job !== null && typeof job === "object" && !Array.isArray(job)).to.eql(true);
        ["title", "city", "description", "source_url"].forEach(function (field) {
            pm.expect(typeof job[field]).to.eql("string");
            pm.expect(job[field].trim().length > 0).to.eql(true);
            pm.expect(job[field]).to.eql(job[field].trim());
        });
        pm.expect(/^https?:\/\/[^\s/]+(?:[/?#][^\s]*)?$/i.test(job.source_url)).to.eql(true);
    });
    // 空数组也是合法结果；逐条检查在此时没有要遍历的元素。
});
