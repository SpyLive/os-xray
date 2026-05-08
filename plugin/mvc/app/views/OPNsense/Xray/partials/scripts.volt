<script>
    $(document).ready(function () {
        // ── Helpers ───────────────────────────────────────────────
        function escAttr(s) {
            return String(s).replace(/[&"<>]/g, function (c) {
                return {'&':'&amp;','"':'&quot;','<':'&lt;','>':'&gt;'}[c];
            });
        }

        // ── Per-instance status overlay ───────────────────────────
        var instanceStatusCache = {};
        var instanceTestCache   = {};

        function statusBadge(info) {
            if (!info) return '<span class="label label-default" style="font-size:11px;">--</span>';
            var xOk = info.xray_core === 'running';
            var tOk = info.tun2socks === 'running';
            return '<span class="label ' + (xOk ? 'label-success' : 'label-danger') + '" style="font-size:11px;">' +
                'xray: ' + (xOk ? 'up' : 'down') +
                '</span> ' +
                '<span class="label ' + (tOk ? 'label-success' : 'label-danger') + '" style="font-size:11px;">' +
                'tun: ' + (tOk ? 'up' : 'down') +
                '</span>';
        }

        function applyStatusToGrid() {
            $('#grid-instances .xray-status-cell').each(function () {
                var uuid = $(this).data('uuid');
                $(this).html(statusBadge(instanceStatusCache[uuid]));
            });
        }

        function testResultBadge(info) {
            if (!info) return '<span style="font-size:11px;color:#999;">--</span>';
            var ok = info.result === 'ok';
            return '<span class="label ' + (ok ? 'label-success' : 'label-danger') + '" style="font-size:11px;">'
                + escAttr(info.message) + '</span>';
        }

        function applyTestResultToGrid() {
            $('#grid-instances .xray-test-cell').each(function () {
                var uuid = $(this).data('uuid');
                $(this).html(testResultBadge(instanceTestCache[uuid]));
            });
        }

        // ── Instances CRUD table (UIBootgrid) ───────────────────────
        $('#grid-instances').UIBootgrid({
            search: '/api/xray/instance/searchItem',
            get:    '/api/xray/instance/getItem/',
            set:    '/api/xray/instance/setItem/',
            add:    '/api/xray/instance/addItem',
            del:    '/api/xray/instance/delItem/',
            toggle: '/api/xray/instance/toggleItem/',
            options: {
                formatters: {
                    instanceStatus: function (column, row) {
                        // TODO: show "disabled" label instead of status badges when row.enabled === '0'
                        return '<span class="xray-status-cell" data-uuid="' + escAttr(row.uuid) + '">' +
                            statusBadge(instanceStatusCache[row.uuid]) + '</span>';
                    },
                    instanceTestResult: function (column, row) {
                        return '<span class="xray-test-cell" data-uuid="' + escAttr(row.uuid) + '">'
                            + testResultBadge(instanceTestCache[row.uuid]) + '</span>';
                    },
                    commands: function (column, row) {
                        // TODO: disable/hide cmd-inst-start and cmd-inst-stop when row.enabled === '0'
                        var uuid = escAttr(row.uuid);
                        return '<button type="button" class="btn btn-xs btn-success cmd-inst-start bootgrid-tooltip"'
                             +   ' data-row-id="' + uuid + '" title="{{ lang._("Start this instance") }}">'
                             +   '<span class="fa fa-play fa-fw"></span></button> '
                             + '<button type="button" class="btn btn-xs btn-danger cmd-inst-stop bootgrid-tooltip"'
                             +   ' data-row-id="' + uuid + '" title="{{ lang._("Stop this instance") }}">'
                             +   '<span class="fa fa-stop fa-fw"></span></button> '
                             + '<button type="button" class="btn btn-xs btn-default cmd-inst-test bootgrid-tooltip"'
                             +   ' data-row-id="' + uuid + '" title="{{ lang._("Test") }}">'
                             +   '<span class="fa fa-plug fa-fw"></span></button> '
                             + '<button type="button" class="btn btn-xs btn-default command-edit bootgrid-tooltip"'
                             +   ' data-row-id="' + uuid + '" title="{{ lang._("Edit") }}">'
                             +   '<span class="fa fa-pencil fa-fw"></span></button> '
                             + '<button type="button" class="btn btn-xs btn-default command-delete bootgrid-tooltip"'
                             +   ' data-row-id="' + uuid + '" title="{{ lang._("Delete") }}">'
                             +   '<span class="fa fa-trash-o fa-fw"></span></button>';
                    }
                }
            }
        });

        // After grid loads/reloads data, fetch and overlay status
        $('#grid-instances').on('loaded.rs.jquery.bootgrid', function () {
            updateStatus();
            // TODO: populate #diagInstanceSelect and #logInstanceSelect from instance list
        });

        // Per-instance start / stop / test (row button handlers)
        $(document).on('click', '#grid-instances .cmd-inst-start', function () {
            instanceServiceAction('start', $(this).data('row-id'));
        });
        $(document).on('click', '#grid-instances .cmd-inst-stop', function () {
            instanceServiceAction('stop', $(this).data('row-id'));
        });
        $(document).on('click', '#grid-instances .cmd-inst-test', function () {
            var uuid = $(this).data('row-id');
            var $btn = $(this).prop('disabled', true);
            $.ajax({
                url: '/api/xray/service/testconnect/' + encodeURIComponent(uuid),
                type: 'POST', dataType: 'json',
                success: function (data) {
                    instanceTestCache[uuid] = data;
                    applyTestResultToGrid();
                },
                complete: function () { $btn.prop('disabled', false); }
            });
        });

        function instanceServiceAction(action, uuid) {
            var url = '/api/xray/service/' + action + (uuid ? '/' + encodeURIComponent(uuid) : '');
            $.ajax({
                url: url, type: 'POST', dataType: 'json',
                success: function () { setTimeout(updateStatus, 1500); }
            });
        }

        // ── General settings form ───────────────────────────────────
        mapDataToFormUI({'frm_general_settings': "/api/xray/general/get"}).done(function () {
            formatTokenizersUI();
            $('.selectpicker').selectpicker('refresh');
        });

        // ── Apply (save general, then reconfigure) ──────────────────
        $("#reconfigureAct").SimpleActionButton({
            onPreAction: function () {
                var dfObj = new $.Deferred();
                saveFormToEndpoint("/api/xray/general/set", 'frm_general_settings', function () {
                    dfObj.resolve();
                });
                return dfObj;
            }
        });

        // ── Status badges + per-instance status ───────────────────
        function updateStatus() {
            ajaxGet("/api/xray/service/statusall", {}, function (data) {
                if (data.error) return;
                instanceStatusCache = data;

                // Aggregate: any instance running = global running
                var anyXray = false, anyTun = false;
                $.each(data, function (uuid, info) {
                    if (info.xray_core === 'running') anyXray = true;
                    if (info.tun2socks === 'running') anyTun = true;
                });
                var xok = anyXray, tok = anyTun;
                $('#badge_xray')
                    .removeClass('label-success label-danger label-default')
                    .addClass(xok ? 'label-success' : 'label-danger')
                    .text('xray-core: ' + (xok ? 'running' : 'stopped'));
                $('#badge_tun')
                    .removeClass('label-success label-danger label-default')
                    .addClass(tok ? 'label-success' : 'label-danger')
                    .text('tun2socks: ' + (tok ? 'running' : 'stopped'));

                // Update per-instance status in grid
                applyStatusToGrid();

                var running = xok || tok;
                $('#btnStartAll').prop('disabled', running);
                $('#btnStopAll').prop('disabled', !running);
                $('#btnRestartAll').prop('disabled', !running);
            });
        }
        updateStatus();
        setInterval(updateStatus, 5000);

        // ── Start / Stop / Restart ──────────────────────────────────
        function serviceAction(action, confirmMsg, callback) {
            if (confirmMsg && !confirm(confirmMsg)) {
                return;
            }
            // TODO: clean up — pass $btn as argument instead of deriving it from action string
            var $btns = $('#btnStartAll, #btnStopAll, #btnRestartAll').prop('disabled', true);
            var $btn = action === 'start'   ? $('#btnStartAll')
                     : action === 'stop'    ? $('#btnStopAll')
                     :                        $('#btnRestartAll');
            var origHtml = $btn.html();
            $btn.html('<i class="fa fa-spinner fa-spin"></i>');

            $.ajax({
                url:      '/api/xray/service/' + action,
                type:     'POST',
                dataType: 'json',
                success: function (data) {
                    $btn.html(origHtml);
                    if (data.result !== 'ok') {
                        alert('{{ lang._("Action failed:") }} ' + (data.message || 'unknown error'));
                    }
                    setTimeout(function () {
                        updateStatus();
                        $btns.prop('disabled', false);
                        if (callback) callback();
                    }, 1500);
                },
                error: function (xhr) {
                    $btn.html(origHtml);
                    $btns.prop('disabled', false);
                    alert('{{ lang._("HTTP error:") }} ' + xhr.status);
                }
            });
        }

        $('#btnStartAll').click(function () {
            serviceAction('start', null, null);
        });
        $('#btnStopAll').click(function () {
            var confirmStop = '{{ lang._("Stop Xray VPN? Active connections will be terminated.") }}';
            serviceAction('stop', confirmStop, null);
        });
        $('#btnRestartAll').click(function () {
            serviceAction('restart', null, null);
        });

        // ── Test Connection ─────────────────────────────────────────
        $('#btnTestConnect').click(function () {
            var $btn = $(this).prop('disabled', true);
            var $res = $('#testConnectResult');

            var uuids = [];
            $.each(instanceStatusCache, function (uuid, info) {
                // TODO: check on enabled status
                if (info.xray_core === 'running') { uuids.push(uuid); }
            });

            if (!uuids.length) {
                $res.removeClass('text-success').addClass('text-danger')
                    .text("{{ lang._('No running instances.') }}");
                $btn.prop('disabled', false);
                return;
            }

            $res.removeClass('text-success text-danger').text("{{ lang._('Testing...') }}");
            var pending = uuids.length;

            $.each(uuids, function (_, uuid) {
                $.ajax({
                    url: '/api/xray/service/testconnect/' + encodeURIComponent(uuid),
                    type: 'POST', dataType: 'json',
                    success: function (data) {
                        instanceTestCache[uuid] = data;
                        applyTestResultToGrid();
                    },
                    complete: function () {
                        pending--;
                        if (pending === 0) {
                            $btn.prop('disabled', false);
                            $res.removeClass('text-success text-danger').text('');
                        }
                    }
                });
            });
        });

        // ── Import VLESS (inside DialogInstance) ──────────────────
        function applyImportToDialog(data) {
            var $dlg = $('#DialogInstance');
            if (data.name) {
                $dlg.find('[id="instance.name"]').val(data.name);
            }
            $dlg.find('[id="instance.outbound_config"]').val(data.outbound_config || '');
        }

        // Inject Import panel + Validate button into DialogInstance on first open
        var dialogInjected = false;
        $('#DialogInstance').on('show.bs.modal', function () {
            if (dialogInjected) {
                // Reset state on each open
                $('#dlgImportLink').val('');
                $('#dlgImportResult').text('').removeClass('text-success text-danger');
                $('#dlgImportPanel').collapse('hide');
                $('#dlgValidateResult').text('').removeClass('text-success text-danger');
                return;
            }
            dialogInjected = true;

            // Import panel — collapsible, injected before the form table
            var importHtml =
                '<div style="margin: 0 0 10px;">' +
                    '<a data-toggle="collapse" href="#dlgImportPanel" class="btn btn-sm btn-default" style="margin-bottom: 6px;">' +
                        '<i class="fa fa-upload"></i> {{ lang._("Import VLESS link") }}' +
                    '</a>' +
                    '<div id="dlgImportPanel" class="collapse">' +
                        '<div class="well well-sm" style="margin-bottom: 0;">' +
                            '<div class="input-group">' +
                                '<input type="text" id="dlgImportLink" class="form-control input-sm"' +
                                '  style="font-family: monospace; font-size: 12px;"' +
                                '  placeholder="vless://UUID@host:443?security=reality&pbk=...#Name" />' +
                                '<span class="input-group-btn">' +
                                    '<button type="button" id="dlgImportParseBtn" class="btn btn-sm btn-primary">' +
                                        '<i class="fa fa-magic"></i> {{ lang._("Parse & Fill") }}' +
                                    '</button>' +
                                '</span>' +
                            '</div>' +
                            '<span id="dlgImportResult" style="font-size: 12px; display: inline-block; margin-top: 4px;"></span>' +
                        '</div>' +
                    '</div>' +
                '</div>';
            var $body = $(this).find('.modal-body');
            $body.prepend(importHtml);

            // Validate button — in footer, before Save
            var validateHtml =
                '<button type="button" id="dlgValidateBtn" class="btn btn-info pull-left">' +
                    '<i class="fa fa-check-circle"></i> {{ lang._("Validate Config") }}' +
                '</button>' +
                '<span id="dlgValidateResult" class="pull-left" style="font-size: 12px; line-height: 34px; margin-left: 8px;"></span>';
            var $footer = $(this).find('.modal-footer');
            $footer.prepend(validateHtml);
        });

        // Import parse handler (inside dialog)
        $(document).on('click', '#dlgImportParseBtn', function () {
            var link = $.trim($('#dlgImportLink').val());
            var $res = $('#dlgImportResult');
            if (!link) {
                $res.removeClass('text-success').addClass('text-danger')
                    .text("{{ lang._('Paste a VLESS link first.') }}");
                return;
            }

            var $btn = $(this).prop('disabled', true);
            $res.removeClass('text-success text-danger').text("{{ lang._('Parsing...') }}");
            var b64 = btoa(unescape(encodeURIComponent(link)));

            $.ajax({
                url:         '/api/xray/import/parse',
                type:        'POST',
                contentType: 'application/json; charset=utf-8',
                data:        JSON.stringify({link_b64: b64}),
                dataType:    'json',
                success: function (data) {
                    $btn.prop('disabled', false);
                    if (data.status !== 'ok') {
                        $res.removeClass('text-success').addClass('text-danger')
                            .text("{{ lang._('Parse error:') }} " + (data.message || 'unknown'));
                        return;
                    }
                    applyImportToDialog(data);
                    $res.removeClass('text-danger').addClass('text-success')
                        .text("{{ lang._('Imported! Fields filled from link.') }}");
                    // Collapse import panel after success
                    setTimeout(function () { $('#dlgImportPanel').collapse('hide'); }, 1500);
                },
                error: function (xhr) {
                    $btn.prop('disabled', false);
                    $res.removeClass('text-success').addClass('text-danger')
                        .text("{{ lang._('HTTP error:') }} " + xhr.status);
                }
            });
        });

        // Enter key in import field triggers parse
        $(document).on('keypress', '#dlgImportLink', function (e) {
            if (e.which === 13) {
                e.preventDefault();
                $('#dlgImportParseBtn').click();
            }
        });

        // ── Validate Config (inside DialogInstance footer) ────────
        $(document).on('click', '#dlgValidateBtn', function () {
            var $btn = $(this).prop('disabled', true);
            var $res = $('#dlgValidateResult');
            $res.removeClass('text-success text-danger').text("{{ lang._('Validating...') }}");

            $.ajax({
                url:      '/api/xray/service/validate',
                type:     'POST',
                dataType: 'json',
                success: function (data) {
                    $btn.prop('disabled', false);
                    if (data.result === 'ok') {
                        $res.removeClass('text-danger').addClass('text-success')
                            .text(data.message || "{{ lang._('Config is valid') }}");
                    } else {
                        $res.removeClass('text-success').addClass('text-danger')
                            .text(data.message || "{{ lang._('Validation failed') }}");
                    }
                },
                error: function (xhr) {
                    $btn.prop('disabled', false);
                    $res.addClass('text-danger').text("{{ lang._('HTTP error:') }} " + xhr.status);
                }
            });
        });

        // ── Diagnostics ─────────────────────────────────────────────
        // TODO: wire #diagInstanceSelect change → reload; populate options from instance list
        function loadDiagnostics() {
            // TODO: read #diagInstanceSelect val, append /{uuid} to URL when set
            $('#btnDiagRefresh').prop('disabled', true);
            $('#diagError').hide();
            ajaxGet('/api/xray/service/diagnostics', {}, function (data) {
                $('#btnDiagRefresh').prop('disabled', false);
                if (data.error) {
                    $('#diagError').text(data.error).show();
                    return;
                }
                var running = data.tun_status === 'running';
                var statusHtml = running
                    ? '<span class="label label-success">running</span>'
                    : '<span class="label label-danger">' + escAttr(data.tun_status || 'down') + '</span>';

                // TODO: audit xray-ifstats backend \u2014 tun_interface, tun_ip, mtu, pkts_in/out not returned
                $('#diag_tun_iface').text(data.tun_interface  || '\u2014');
                $('#diag_tun_status').html(statusHtml);
                $('#diag_tun_ip').text(data.tun_ip           || '\u2014');
                $('#diag_mtu').text(data.mtu > 0 ? data.mtu + ' bytes' : '\u2014');
                // TODO: bytes_in_hr/bytes_out_hr not human-readable \u2014 convert raw bytes to MB/GB in backend or here
                $('#diag_bytes_in').text(data.bytes_in_hr    || '\u2014');
                $('#diag_bytes_out').text(data.bytes_out_hr  || '\u2014');
                $('#diag_pkts_in').text(data.pkts_in != null ? data.pkts_in.toLocaleString() : '\u2014');
                $('#diag_pkts_out').text(data.pkts_out != null ? data.pkts_out.toLocaleString() : '\u2014');
                // TODO: xray_uptime, tun2socks_uptime, ping_rtt not returned by ifstats \u2014 fix backend script
                $('#diag_xray_uptime').text(data.xray_uptime || '\u2014');
                $('#diag_t2s_uptime').text(data.tun2socks_uptime || '\u2014');
                $('#diag_ping_rtt').text(data.ping_rtt || 'N/A');
            });
        }

        var diagAutoRefresh = null;
        $('a[href="#diagnostics"]').on('shown.bs.tab', function () {
            loadDiagnostics();
            if (!diagAutoRefresh) {
                diagAutoRefresh = setInterval(function () {
                    if ($('#diagnostics').hasClass('active')) {
                        loadDiagnostics();
                    }
                }, 30000);
            }
        });
        $('#btnDiagRefresh').click(function () {
            loadDiagnostics();
        });

        // TODO: wire #logInstanceSelect change → reload active log tab; populate options from instance list
        // ── Logs ────────────────────────────────────────────────────
        function loadLog(apiEndpoint, preId, btnId) {
            // TODO: add UUID parameter for per-instance log using #logInstanceSelect
            $('#' + btnId).prop('disabled', true);
            $('#' + preId).text("{{ lang._('Loading...') }}");
            $.post(apiEndpoint, null, function (data) {
                var text = (data && data.log) || "{{ lang._('Log is empty.') }}";
                $('#' + preId).text(text);
                $('#' + btnId).prop('disabled', false);
                var pre = document.getElementById(preId);
                if (pre) { pre.scrollTop = pre.scrollHeight; }
            }, 'json').fail(function (xhr) {
                $('#' + preId).text("{{ lang._('Error loading log:') }} " + xhr.status);
                $('#' + btnId).prop('disabled', false);
            });
        }

        $('a[href="#logs"]').on('shown.bs.tab', function () {
            var $active = $('#logSubTabs .active a');
            var href = $active.attr('href');
            if (href === '#logBoot') {
                loadLog("/api/xray/service/log", 'logBootContent', 'logBootRefreshBtn');
            } else if (href === '#logCore') {
                loadLog("/api/xray/service/xraylog", 'logCoreContent', 'logCoreRefreshBtn');
            }
        });

        $('#logSubTabs a').on('shown.bs.tab', function (e) {
            var href = $(e.target).attr('href');
            if (href === '#logBoot') {
                loadLog("/api/xray/service/log", 'logBootContent', 'logBootRefreshBtn');
            } else if (href === '#logCore') {
                loadLog("/api/xray/service/xraylog", 'logCoreContent', 'logCoreRefreshBtn');
            }
        });

        $("#logBootRefreshBtn").click(function () {
            loadLog("/api/xray/service/log", 'logBootContent', 'logBootRefreshBtn');
        });
        $("#logCoreRefreshBtn").click(function () {
            loadLog("/api/xray/service/xraylog", 'logCoreContent', 'logCoreRefreshBtn');
        });

        // ── Copy Debug Info ─────────────────────────────────────────
        $('#btnCopyDebug').click(function () {
            var $btn = $(this).prop('disabled', true);
            var $res = $('#copyDebugResult');
            $res.removeClass('text-success text-danger').text("{{ lang._('Collecting...') }}");

            var diagData = {}, bootLog = '', coreLog = '';
            var diagDone = $.Deferred(), bootDone = $.Deferred(), coreDone = $.Deferred();

            ajaxGet('/api/xray/service/diagnostics', {}, function (data) {
                diagData = data;
                diagDone.resolve();
            });
            $.post('/api/xray/service/log', null, function (data) {
                bootLog = (data && data.log) || '';
                bootDone.resolve();
            }, 'json').fail(function () { bootDone.resolve(); });
            $.post('/api/xray/service/xraylog', null, function (data) {
                coreLog = (data && data.log) || '';
                coreDone.resolve();
            }, 'json').fail(function () { coreDone.resolve(); });

            $.when(diagDone, bootDone, coreDone).done(function () {
                var info = "=== os-xray Debug Info ===\n"
                    + "Date: " + new Date().toISOString() + "\n\n"
                    + "--- Diagnostics ---\n"
                    + JSON.stringify(diagData, null, 2) + "\n\n"
                    + "--- Boot Log (last 150 lines) ---\n"
                    + bootLog + "\n\n"
                    + "--- Core Log (last 200 lines) ---\n"
                    + coreLog + "\n";

                $('#debugInfoContent').val(info);
                $('#debugInfoModal').modal('show');
                $('#debugInfoModal').one('shown.bs.modal', function () {
                    var ta = document.getElementById('debugInfoContent');
                    ta.focus();
                    ta.select();
                });
                $res.addClass('text-success').text("{{ lang._('Use Ctrl+C / Cmd+C to copy') }}");
                $btn.prop('disabled', false);
            });
        });

        // ── Tab hash ────────────────────────────────────────────────
        if (window.location.hash !== "") {
            $('a[href="' + window.location.hash + '"]').click();
        }
        $('.nav-tabs a').on('shown.bs.tab', function (e) {
            history.pushState(null, null, e.target.hash);
        });
    });
</script>
