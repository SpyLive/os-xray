<!-- LOGS -->
<div id="logs" class="tab-pane fade in">

    {# ── Toolbar ─────────────────────────────────────────────────────── #}
    <div class="row">
        <section class="col-xs-12">
            <div style="padding: 8px 15px; border-bottom: 1px solid #ddd;
                        display: flex; flex-wrap: wrap; align-items: center; gap: 8px;">

                {# Instance selector #}
                {# TODO: populate from instance list; wire change → reload active log tab with selected UUID #}
                <div class="input-group input-group-sm" style="max-width: 260px;">
                    <span class="input-group-addon">
                        <i class="fa fa-server fa-fw"></i>
                    </span>
                    <select id="logInstanceSelect" class="form-control">
                        <option value="">{{ lang._('— all instances —') }}</option>
                    </select>
                </div>

                <div style="width: 1px; height: 22px; background: #ddd;"></div>

                {# Log type sub-tabs #}
                <ul class="nav nav-pills nav-sm" id="logSubTabs" style="margin: 0;">
                    <li class="active">
                        <a data-toggle="tab" href="#logBoot">
                            <i class="fa fa-terminal fa-fw"></i> {{ lang._('Boot Log') }}
                        </a>
                    </li>
                    <li>
                        <a data-toggle="tab" href="#logCore">
                            <i class="fa fa-file-text-o fa-fw"></i> {{ lang._('Core Log') }}
                        </a>
                    </li>
                </ul>

            </div>
        </section>
    </div>

    {# ── Log panes ───────────────────────────────────────────────────── #}
    <div class="row">
        <section class="col-xs-12">
            <div class="tab-content" style="padding: 0 15px 15px;">

                <div id="logBoot" class="tab-pane fade in active" style="padding-top: 10px;">
                    <div style="margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
                        <button id="logBootRefreshBtn" class="btn btn-sm btn-default">
                            <i class="fa fa-refresh fa-fw"></i> {{ lang._('Refresh') }}
                        </button>
                        <span class="text-muted" style="font-size: 12px;">
                            {{ lang._('/tmp/xray_syshook.log — last 150 lines') }}
                        </span>
                    </div>
                    <pre id="logBootContent"
                         style="min-height: 300px; max-height: 550px; overflow-y: auto;
                                background: #1e1e1e; color: #d4d4d4; font-family: monospace;
                                font-size: 12px; padding: 12px; border-radius: 4px;
                                border: 1px solid #444;">{{ lang._('Switch to this tab to load log.') }}</pre>
                </div>

                <div id="logCore" class="tab-pane fade in" style="padding-top: 10px;">
                    <div style="margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
                        <button id="logCoreRefreshBtn" class="btn btn-sm btn-default">
                            <i class="fa fa-refresh fa-fw"></i> {{ lang._('Refresh') }}
                        </button>
                        <span class="text-muted" style="font-size: 12px;">
                            {{ lang._('/var/log/xray-core-{uuid}.log — last 200 lines') }}
                        </span>
                    </div>
                    <pre id="logCoreContent"
                         style="min-height: 300px; max-height: 550px; overflow-y: auto;
                                background: #1e1e1e; color: #d4d4d4; font-family: monospace;
                                font-size: 12px; padding: 12px; border-radius: 4px;
                                border: 1px solid #444;">{{ lang._('Click "Core Log" to load.') }}</pre>
                </div>

            </div>
        </section>
    </div>

</div>
