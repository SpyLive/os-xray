<!-- DIAGNOSTICS -->
<div id="diagnostics" class="tab-pane fade in">
    <div style="padding: 12px 15px 4px; display: flex; align-items: center; gap: 8px;">
        <button id="btnDiagRefresh" class="btn btn-sm btn-default">
            <i class="fa fa-refresh"></i> {{ lang._('Refresh') }}
        </button>
        <button id="btnCopyDebug" class="btn btn-sm btn-default">
            <i class="fa fa-clipboard"></i> {{ lang._('Copy Debug Info') }}
        </button>
        <span id="copyDebugResult" style="font-size: 12px;"></span>
        <span class="text-muted" style="font-size: 12px;">{{ lang._('TUN interface stats and process uptime') }}</span>
    </div>

    <div style="padding: 8px 15px 15px;">
        <table class="table table-condensed table-striped" style="max-width: 600px;">
            <tbody>
                <tr><th style="width:220px;">{{ lang._('TUN Interface') }}</th><td id="diag_tun_iface">&mdash;</td></tr>
                <tr><th>{{ lang._('TUN Status') }}</th><td id="diag_tun_status">&mdash;</td></tr>
                <tr><th>{{ lang._('TUN IP') }}</th><td id="diag_tun_ip">&mdash;</td></tr>
                <tr><th>{{ lang._('MTU') }}</th><td id="diag_mtu">&mdash;</td></tr>
                <tr><th>{{ lang._('Bytes In') }}</th><td id="diag_bytes_in">&mdash;</td></tr>
                <tr><th>{{ lang._('Bytes Out') }}</th><td id="diag_bytes_out">&mdash;</td></tr>
                <tr><th>{{ lang._('Packets In') }}</th><td id="diag_pkts_in">&mdash;</td></tr>
                <tr><th>{{ lang._('Packets Out') }}</th><td id="diag_pkts_out">&mdash;</td></tr>
                <tr><th>{{ lang._('xray-core Uptime') }}</th><td id="diag_xray_uptime">&mdash;</td></tr>
                <tr><th>{{ lang._('tun2socks Uptime') }}</th><td id="diag_t2s_uptime">&mdash;</td></tr>
                <tr><th>{{ lang._('Server Ping RTT') }}</th><td id="diag_ping_rtt">&mdash;</td></tr>
            </tbody>
        </table>
        <p id="diagError" class="text-danger" style="display:none;"></p>
    </div>
</div>
