#!/usr/local/bin/php
<?php
// Administrative Stop and component recovery are serialized by the controller.
$ctrl=__DIR__.'/xray-service-control.php';
exec('/usr/local/bin/php '.escapeshellarg($ctrl).' watchdog 2>&1',$out,$rc);
$output=trim(implode("\n",$out));
if ($rc !== 0 || ($output !== '' && $output !== 'OK')) {
    file_put_contents('/var/log/xray-watchdog.log',date('[Y-m-d H:i:s]').' exit='.$rc.' '.$output."\n",FILE_APPEND|LOCK_EX);
}
if ($output !== '') echo $output."\n";
exit($rc);
