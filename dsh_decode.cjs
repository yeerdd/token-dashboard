// DSH 会话 zstd 解码器（供 collectors.py 调用）
// 用法: node dsh_decode.cjs <session.jsonl.zstd>  → 输出解码后的 JSONL 到 stdout
const zlib = require('zlib');
const fs = require('fs');

const file = process.argv[2];
if (!file || !fs.existsSync(file)) {
  process.stderr.write('FILE_NOT_FOUND:' + file + '\n');
  process.exit(1);
}

const buf = fs.readFileSync(file);
const magic = Buffer.from([0x28, 0xB5, 0x2F, 0xFD]);
const out = [];
let pos = 0;
while (pos < buf.length - 4) {
  const idx = buf.indexOf(magic, pos);
  if (idx < 0) break;
  const next = buf.indexOf(magic, idx + 4);
  const end = next < 0 ? buf.length : next;
  try {
    out.push(zlib.zstdDecompressSync(buf.subarray(idx, end)).toString('utf8'));
  } catch (e) {
    // skip bad frame
  }
  pos = end;
}
if (out.length === 0) {
  process.stderr.write('NO_FRAMES\n');
  process.exit(2);
}
process.stdout.write(out.join('\n'));
