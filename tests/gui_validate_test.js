/* Execute production dialog helpers/callbacks with small DOM/AJAX adapters.
 * This is not an OPNsense browser integration test.
 */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,
    '../plugin/mvc/app/views/OPNsense/Xray/partials/scripts.volt'), 'utf8');
const rendered = source.replace(/{{\s*lang\._\((["'])(.*?)\1\)\s*}}/g, 'Translated text');
new vm.Script(rendered.replace(/^<script>\s*/, '').replace(/<\/script>\s*$/, ''));
assert.match(source, /options:\s*{\s*onBeforeRenderDialog: savedDialogLoaded/);
assert.match(source, /Unsaved changes are not validated/);
assert.match(source, /id="dlgValidateBtn" disabled/);
const helpers = rendered.slice(rendered.indexOf('        var validationDialogUuid'),
    rendered.indexOf('        // ── Instances CRUD table'));
const handler = rendered.slice(rendered.indexOf("        $(document).on('click', '#dlgValidateBtn'"),
    rendered.indexOf('        // ── Diagnostics'));
const states = new Map();
let click;
const requests = [];
function $(selector) {
    if (!states.has(selector)) {
        const obj = {disabled: true, value: '',
            prop(key, value) { this[key] = value; return this; },
            text(value) { this.value = value; return this; },
            removeClass() { return this; }, addClass() { return this; },
            on(event, target, callback) { click = callback; return this; }};
        states.set(selector, obj);
    }
    return states.get(selector);
}
$.Deferred = () => ({resolve() { return {promise() { return {}; }}; }});
$.ajax = request => requests.push(request);
const context = vm.createContext({$, document: {}});
vm.runInContext(helpers + handler, context);
const A = '00000000-0000-4000-8000-000000000001';
const B = '00000000-0000-4000-8000-000000000002';
const load = uuid => context.savedDialogLoaded({frm_DialogInstance: {instance_uuid: uuid}});
const press = () => click.call('#dlgValidateBtn');
load(B); press();
assert.equal(requests[0].url, '/api/xray/service/validate/' + B);
assert.equal(requests[0].type, 'POST');
requests[0].success({result: 'ok', message: 'B saved valid'});
assert.equal($('#dlgValidateResult').value, 'B saved valid');
console.log('GUI Validate selected second instance: PASS');
context.resetDialogValidation(); load(''); press();
assert.equal(requests.length, 1);
assert.equal($('#dlgValidateBtn').disabled, true);
console.log('GUI Validate new unsaved instance: no request: PASS');
context.resetDialogValidation(); load(A); press();
const stale = requests[1];
context.resetDialogValidation(); load(B);
stale.success({result: 'ok', message: 'wrong instance'});
assert.equal($('#dlgValidateResult').value, '');
stale.error({status: 500});
assert.equal($('#dlgValidateResult').value, '');
console.log('GUI Validate late responses after dialog change ignored: PASS');
context.resetDialogValidation(); load('invalid'); press();
assert.equal(requests.length, 2);
console.log('GUI Validate invalid identity: no request: PASS');
