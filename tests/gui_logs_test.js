/* Static markup + production select-population code with DOM/AJAX adapters.
 * No browser layout engine: visual alignment must be checked on OPNsense.
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const views = path.join(__dirname, '../plugin/mvc/app/views/OPNsense/Xray/partials');
const page = fs.readFileSync(path.join(views, '../general.volt'), 'utf8');
assert.match(page, /id="xray-instance-tabs"/);
const css = page.match(/<style>([\s\S]*?)<\/style>/)[1].replace(/\/\*[\s\S]*?\*\//g, '');
const rules = [...css.matchAll(/([^{}]+)\{([^{}]+)\}/g)];
assert.equal(rules.length, 3);
for (const [, selector] of rules) {
    assert.ok(selector.trim().startsWith('#xray-instance-tabs .xray-instance-selector'));
    assert.ok(!selector.includes(',')); // No unscoped selector in a selector list.
}
assert.match(rules[0][2], /flex: 0 1 260px/);
assert.match(rules[0][2], /max-width: 100%/);
assert.match(rules[0][2], /min-width: 0/);
assert.match(rules[0][2], /table-layout: fixed/);
assert.equal(rules[2][1].trim(), '#xray-instance-tabs .xray-instance-selector > select.form-control');
assert.match(rules[2][2], /line-height: normal/);
assert.match(rules[2][2], /text-overflow: ellipsis/);
assert.match(rules[2][2], /white-space: nowrap/);
for (const [file, id] of [['tab_logs.volt', 'logInstanceSelect'], ['tab_diagnostics.volt', 'diagInstanceSelect']]) {
    const markup = fs.readFileSync(path.join(views, file), 'utf8');
    const selects = markup.match(/<select\b[^>]*>/g);
    assert.equal(selects.length, 1);
    assert.ok(selects[0].includes('id="' + id + '"'));
    assert.match(selects[0], /class="form-control"/);
    assert.doesNotMatch(selects[0], /style=/); // One shared style source.
    assert.match(markup, /<div class="input-group input-group-sm xray-instance-selector">\s*<span class="input-group-addon">[\s\S]*?<\/span>\s*<select/);
    assert.match(markup, /flex-wrap: wrap/);
    assert.doesNotMatch(markup, /<style\b/);
    console.log('GUI-01 ' + id + ': shared scoped styling and bounded toolbar: PASS (static)');
}

const source = fs.readFileSync(path.join(views, 'scripts.volt'), 'utf8');
const population = source.slice(source.indexOf('        function populateInstanceSelects()'),
    source.indexOf('        function loadDiagnostics()'));
class Select {
    constructor() { this.options = []; this.value = ''; }
    val(value) { if (value === undefined) return this.value; this.value = value; return this; }
    empty() { this.options = []; this.value = ''; return this; }
    append(option) { this.options.push(option); if (!this.value) this.value = option.value; return this; }
    find(selector) {
        const value = selector.match(/option\[value="([^"]+)"\]/)[1];
        return {length: this.options.filter(option => option.value === value).length};
    }
}
const diag = new Select(), logs = new Select();
function $(selector) {
    if (selector === '#diagInstanceSelect') return diag;
    if (selector === '#logInstanceSelect') return logs;
    assert.equal(selector, '<option></option>');
    return {val(value) { this.value = value; return this; },
        text(value) { this.label = value; return this; }};
}
let rows;
$.ajax = request => {
    assert.equal(request.url, '/api/xray/instance/searchItem');
    request.success({rows});
};
$.each = (items, callback) => items.forEach((item, index) => callback(index, item));
const context = vm.createContext({$});
vm.runInContext(population, context);
const A = '00000000-0000-4000-8000-000000000001';
const B = '00000000-0000-4000-8000-000000000002';
const longName = 'Synthetic instance ' + 'Длинное имя <>& '.repeat(30);
rows = [{uuid: A, name: 'Synthetic A'}, {uuid: B, name: longName}];
logs.val(B); diag.val(A);
context.populateInstanceSelects();
assert.equal(logs.val(), B);
assert.equal(diag.val(), A);
for (const select of [diag, logs]) {
    assert.equal(select.options[1].label, longName); // Not shortened or interpreted as HTML.
    assert.equal(select.options[1].value, B);
}
logs.val(A); diag.val(B);
context.populateInstanceSelects();
assert.equal(logs.val(), A);
assert.equal(diag.val(), B);
console.log('GUI Log/Diagnostics: long Unicode names preserved as text; selected UUID unchanged: PASS');
rows = [{uuid: A, name: ''}];
context.populateInstanceSelects();
for (const select of [diag, logs]) {
    assert.equal(select.val(), A);
    assert.equal(select.options[0].label, A);
}
rows = [];
context.populateInstanceSelects();
for (const select of [diag, logs]) {
    assert.equal(select.options.length, 0);
    assert.equal(select.val(), '');
}
console.log('GUI Log/Diagnostics: removed selection, UUID label fallback and empty list: PASS');
