<!-- INSTANCES -->
<div id="instances" class="tab-pane fade in active">
    {# Status bar + service controls #}
    <div style="padding: 10px 15px 6px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px;">
        <span id="badge_xray" class="label label-default">xray-core: ...</span>
        <span id="badge_tun"  class="label label-default">tun2socks: ...</span>

        <span style="margin-left: 4px; border-left: 1px solid #ddd; padding-left: 8px; display: inline-flex; gap: 4px;">
            <button id="btnStart" class="btn btn-xs btn-success" title="{{ lang._('Start all instances') }}">
                <i class="fa fa-play"></i> {{ lang._('Start') }}
            </button>
            <button id="btnStop" class="btn btn-xs btn-danger" title="{{ lang._('Stop all instances') }}">
                <i class="fa fa-stop"></i> {{ lang._('Stop') }}
            </button>
            <button id="btnRestart" class="btn btn-xs btn-warning" title="{{ lang._('Restart without saving config') }}">
                <i class="fa fa-refresh"></i> {{ lang._('Restart') }}
            </button>
        </span>

        <span style="border-left: 1px solid #ddd; padding-left: 8px;">
            <button id="testConnectBtn" class="btn btn-xs btn-default" style="vertical-align: baseline;">
                <i class="fa fa-plug"></i> {{ lang._('Test Connection') }}
            </button>
        </span>
        <span id="testConnectResult" style="font-size: 12px;"></span>
    </div>


    {# Bootgrid instances table #}
    <table id="grid-instances" class="table table-condensed table-hover table-striped"
           data-editDialog="DialogInstance" data-editAlert="InstanceChangeMessage">
        <thead>
            <tr>
                <th data-column-id="uuid" data-type="string" data-identifier="true" data-visible="false">{{ lang._('ID') }}</th>
                <th data-column-id="name" data-type="string">{{ lang._('Name') }}</th>
                <th data-column-id="server_address" data-type="string">{{ lang._('Server') }}</th>
                <th data-column-id="server_port" data-type="string" data-width="80px">{{ lang._('Port') }}</th>
                <th data-column-id="config_mode" data-type="string" data-width="100px">{{ lang._('Mode') }}</th>
                <th data-column-id="inst_status" data-formatter="instanceStatus" data-sortable="false" data-width="180px">{{ lang._('Status') }}</th>
                <th data-column-id="commands" data-formatter="commands" data-sortable="false" data-width="120px">{{ lang._('') }}</th>
            </tr>
        </thead>
        <tbody></tbody>
        <tfoot>
            <tr>
                <td></td>
                <td>
                    <button data-action="add" type="button" class="btn btn-xs btn-primary">
                        <span class="fa fa-fw fa-plus"></span>
                    </button>
                    <button data-action="deleteSelected" type="button" class="btn btn-xs btn-default">
                        <span class="fa fa-fw fa-trash-o"></span>
                    </button>
                </td>
            </tr>
        </tfoot>
    </table>
    <div id="InstanceChangeMessage" class="alert alert-info" style="display: none;" role="alert">
        {{ lang._('Changes saved. Click Apply below to activate.') }}
    </div>
</div>