import { Buffer } from "node:buffer";
import { crc32, deflateSync } from "node:zlib";

const SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

/** One chunk of a PNG: the length of its data, its name and data, and the checksum of those two. */
function chunk(type: string, data: Buffer): Buffer {
  const named = Buffer.concat([Buffer.from(type, "latin1"), data]);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(named));
  return Buffer.concat([length, named, checksum]);
}

/**
 * A whole PNG of one flat grey at the size asked.
 *
 * A page is to be measured with a picture as wide and tall as the one it will be handed: a
 * screenshot is a thousand pixels across, and one of a whole page many times taller than
 * wide. Flat, it is a few kilobytes whatever its size.
 */
export function flatPng(width: number, height: number): Buffer {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  // Eight bits of grey a pixel; the three zeroes after it are the only values PNG has.
  header.writeUInt8(8, 8);
  // Each row is a byte that says "not filtered" and then a byte for each pixel.
  const rows = Buffer.alloc(height * (width + 1), 0xcc);
  for (let row = 0; row < height; row += 1) rows[row * (width + 1)] = 0;
  return Buffer.concat([SIGNATURE, chunk("IHDR", header), chunk("IDAT", deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}
