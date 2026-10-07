// 仅用于回归仓库中已有脚本：不是完整 Apifox/Postman 运行时。
// Python 通过标准输入传入合成样本的 HTTP 响应，不读取任何环境凭据。
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
let count = 0;
for (const entry of cases) {
    const pm = {
        response: {
            code: entry.status,
            headers: {get: name => entry.headers[name.toLowerCase()]},
            json: () => JSON.parse(entry.body),
        },
        expect: actual => ({to: {eql: expected => {
            // VM 与主进程的对象原型不同，JSON 归一化后比较响应值。
            assert.deepStrictEqual(JSON.parse(JSON.stringify(actual)),
                                   JSON.parse(JSON.stringify(expected)));
        }}}),
        test: (name, callback) => {
            try { callback(); count++; }
            catch { throw new Error(`${entry.name}：${name} 断言失败`); }
        },
    };
    vm.runInNewContext(entry.script, {pm}, {timeout: 1000});
}
process.stdout.write(JSON.stringify({requests: cases.length, assertions: count}));
