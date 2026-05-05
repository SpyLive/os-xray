<!-- Debug Info Modal -->
<div class="modal fade" id="debugInfoModal" tabindex="-1" role="dialog">
    <div class="modal-dialog modal-lg">
        <div class="modal-content">
            <div class="modal-header">
                <button type="button" class="close" data-dismiss="modal"><span>&times;</span></button>
                <h4 class="modal-title">
                    <i class="fa fa-clipboard"></i> {{ lang._('Debug Info') }}
                </h4>
            </div>
            <div class="modal-body">
                <p class="text-muted">
                    {{ lang._('Select all (Ctrl+A / Cmd+A) and copy (Ctrl+C / Cmd+C), then paste into your issue report.') }}
                </p>
                <textarea id="debugInfoContent" readonly cols="1000"
                          style="font-family: monospace; font-size: 11px; width: 100% !important; min-width: 100% !important; max-width: 100% !important; height: 70vh; resize: vertical; background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 4px; border: 1px solid #444; display: block; box-sizing: border-box; white-space: pre; overflow-x: auto;"></textarea>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-default" data-dismiss="modal">{{ lang._('Close') }}</button>
            </div>
        </div>
    </div>
</div>