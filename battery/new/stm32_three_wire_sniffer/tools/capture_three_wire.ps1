param(
  [Parameter(Mandatory=$true)]
  [string]$Port,

  [int]$Baud = 1000000,
  [double]$Seconds = 60,
  [string]$Out = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Out)) {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $Out = ".\captures\capture_three_wire_$stamp.bin"
}

$outDir = Split-Path -Parent $Out
if ($outDir) {
  New-Item -ItemType Directory -Force $outDir | Out-Null
}

$serial = [System.IO.Ports.SerialPort]::new($Port, $Baud, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
$serial.ReadTimeout = 100
$serial.Open()

$fs = [System.IO.File]::Open($Out, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
$buffer = New-Object byte[] 4096
$parse = New-Object System.Collections.Generic.List[byte]
$start = Get-Date
$lastPrint = Get-Date "2000-01-01"
$edgeCounts = @(0, 0, 0)
$lastLevels = @(0, 0, 0)

Write-Host "capturing $Port at $Baud, output=$Out"

try {
  while (((Get-Date) - $start).TotalSeconds -lt $Seconds) {
    try {
      $n = $serial.Read($buffer, 0, $buffer.Length)
    } catch [TimeoutException] {
      $n = 0
    }

    if ($n -gt 0) {
      $fs.Write($buffer, 0, $n)
      for ($i = 0; $i -lt $n; $i++) {
        $parse.Add($buffer[$i])
      }
    }

    while ($parse.Count -ge 2) {
      if ($parse[0] -ne 0xA5 -or $parse[1] -ne 0x5A) {
        $found = -1
        for ($i = 1; $i -lt ($parse.Count - 1); $i++) {
          if ($parse[$i] -eq 0xA5 -and $parse[$i + 1] -eq 0x5A) {
            $found = $i
            break
          }
        }
        if ($found -lt 0) {
          $parse.RemoveRange(0, [Math]::Max(1, $parse.Count - 1))
        } else {
          $parse.RemoveRange(0, $found)
        }
        continue
      }

      if ($parse.Count -lt 5) { break }

      $type = $parse[2]
      $len = $parse[3]
      $frameLen = 2 + 1 + 1 + $len + 1
      if ($parse.Count -lt $frameLen) { break }

      $bytes = $parse.GetRange(0, $frameLen).ToArray()
      $parse.RemoveRange(0, $frameLen)

      $crc = $type -bxor $len
      for ($i = 0; $i -lt $len; $i++) {
        $crc = $crc -bxor $bytes[4 + $i]
      }
      if (($crc -band 0xFF) -ne $bytes[$frameLen - 1]) {
        continue
      }

      if ($type -eq 0xE1 -and $len -eq 15) {
        $payload = $bytes[4..(4 + $len - 1)]
        $ch = $payload[0]
        $level = $payload[1]
        if ($ch -ge 0 -and $ch -lt 3) {
          $edgeCounts[$ch]++
          $lastLevels[$ch] = $level
        }
        if (((Get-Date) - $lastPrint).TotalMilliseconds -ge 500) {
          $lastPrint = Get-Date
          "edge-stream levels S/V/G={0}/{1}/{2} edge_packets S/V/G={3}/{4}/{5}" -f $lastLevels[0], $lastLevels[1], $lastLevels[2], $edgeCounts[0], $edgeCounts[1], $edgeCounts[2]
        }
      } elseif ($type -eq 0x5A -and $len -eq 23) {
        $payload = $bytes[4..(4 + $len - 1)]
        $levels = $payload[0]
        $flags = $payload[1]
        $tick = [BitConverter]::ToUInt32($payload, 3)
        $c0 = [BitConverter]::ToUInt32($payload, 7)
        $c1 = [BitConverter]::ToUInt32($payload, 11)
        $c2 = [BitConverter]::ToUInt32($payload, 15)
        $drop = [BitConverter]::ToUInt32($payload, 19)
        if (((Get-Date) - $lastPrint).TotalMilliseconds -ge 500) {
          $lastPrint = Get-Date
          $s = $levels -band 1
          $v = ($levels -shr 1) -band 1
          $g = ($levels -shr 2) -band 1
          "{0,8:N3}s levels S/V/G={1}/{2}/{3} edges S/V/G={4}/{5}/{6} dropped={7} flags={8}" -f ($tick / 1000000.0), $s, $v, $g, $c0, $c1, $c2, $drop, $flags
        }
      }
    }
  }
} finally {
  $fs.Close()
  $serial.Close()
}

Write-Host "done. saved=$Out"
