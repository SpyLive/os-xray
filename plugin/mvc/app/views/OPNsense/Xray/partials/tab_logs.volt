<!-- LOGS -->
<div id="logs" class="tab-pane fade in">
    <div style="padding: 10px 15px 0;">
        <ul class="nav nav-pills" id="logSubTabs" style="margin-bottom: 0;">
            <li class="active">
                <a data-toggle="tab" href="#logBoot">
                    <i class="fa fa-terminal"></i> {{ lang._('Boot Log') }}
                </a>
            </li>
            <li>
                <a data-toggle="tab" href="#logCore">
                    <i class="fa fa-file-text-o"></i> {{ lang._('Xray Core Log') }}
                </a>
            </li>
        </ul>
    </div>

    <div class="tab-content" style="padding: 0 15px 15px;">
        <div id="logBoot" class="tab-pane fade in active" style="padding-top: 10px;">
            <div style="margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
                <button id="logBootRefreshBtn" class="btn btn-sm btn-default">
                    <i class="fa fa-refresh"></i> {{ lang._('Refresh') }}
                </button>
                <span class="text-muted" style="font-size: 12px;">
                    {{ lang._('/tmp/xray_syshook.log — last 150 lines') }}
                </span>
            </div>
            <pre id="logBootContent"
                 style="min-height: 300px; max-height: 550px; overflow-y: auto;
                        background: #1e1e1e; color: #d4d4d4;
                        font-family: monospace; font-size: 12px;
                        padding: 12px; border-radius: 4px; border: 1px solid #444;">{{ lang._('Switch to this tab to load log.') }}</pre>
        </div>

        <div id="logCore" class="tab-pane fade in" style="padding-top: 10px;">
            <div style="margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
                <button id="logCoreRefreshBtn" class="btn btn-sm btn-default">
                    <i class="fa fa-refresh"></i> {{ lang._('Refresh') }}
                </button>
                <span class="text-muted" style="font-size: 12px;">
                    {{ lang._('/var/log/xray-core.log — last 200 lines (rotated at 600 KB)') }}
                </span>
            </div>
            <pre id="logCoreContent"
                 style="min-height: 300px; max-height: 550px; overflow-y: auto;
                        background: #1e1e1e; color: #d4d4d4;
                        font-family: monospace; font-size: 12px;
                        padding: 12px; border-radius: 4px; border: 1px solid #444;">{{ lang._('Click "Xray Core Log" tab to load.') }}</pre>
        </div>
    </div>
</div>