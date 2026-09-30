#!/usr/bin/env node
// wxapkg 解包：经典格式 0xBE 头 + 文件索引表
const fs = require('fs');
const path = require('path');

const src = process.argv[2];
const outDir = process.argv[3] || 'unpacked';
const buf = fs.readFileSync(src);

if (buf[0] !== 0xbe) { console.error('not a plain wxapkg (firstMark=0x' + buf[0].toString(16) + ')，可能是加密包'); process.exit(1); }
if (buf[14] !== 0xed) { console.error('lastMark mismatch: 0x' + buf[14].toString(16)); process.exit(1); }

const fileCount = buf.readUInt32BE(15);
let p = 19;
const files = [];
for (let i = 0; i < fileCount; i++) {
  const nameLen = buf[p++];
  const name = buf.toString('utf8', p, p + nameLen); p += nameLen;
  const off = buf.readUInt32BE(p); p += 4;
  const size = buf.readUInt32BE(p); p += 4;
  files.push({ name, off, size });
}
fs.mkdirSync(outDir, { recursive: true });
for (const f of files) {
  const dest = path.join(outDir, f.name.replace(/^\/+/, ''));
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, buf.subarray(f.off, f.off + f.size));
}
console.log(`unpacked ${files.length} files -> ${outDir}`);
for (const f of files.slice(0, 60)) console.log(`  ${f.size}\t${f.name}`);
if (files.length > 60) console.log(`  ... and ${files.length - 60} more`);
