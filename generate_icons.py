# Generate simple PWA icons
import struct, zlib

def create_png(size):
    """Create a simple solid-color PNG icon"""
    # RGBA: dark blue background with a clock icon in cyan
    width = height = size
    
    # Create raw pixel data (RGBA)
    pixels = []
    for y in range(height):
        row = []
        for x in range(width):
            # Dark background
            r, g, b, a = 15, 15, 35, 255  # #0f0f23
            
            # Clock circle
            cx, cy = width//2, height//2
            radius = width//2 - 4
            dist = ((x - cx)**2 + (y - cy)**2) ** 0.5
            
            if dist <= radius:
                r, g, b = 26, 26, 46  # #1a1a2e
                
            # Clock rim
            if abs(dist - radius) < 2:
                r, g, b = 79, 195, 247  # #4fc3f7
                
            # Clock hands (12 o'clock and 3 o'clock)
            if dist < radius - 3:
                # Hour hand pointing to ~10 o'clock
                hx = cx + int(3 * (x - cx) / max(dist, 1))
                hy = cy + int(3 * (y - cy) / max(dist, 1))
                if dist > 2 and abs((x - cx) * 0.5 + (y - cy) * 0.866) < 2 and (x-cx)**2 + (y-cy)**2 < (radius*0.4)**2:
                    r, g, b = 79, 195, 247
                # Minute hand pointing to 12
                if dist > 2 and abs(x - cx) < 1.5 and (y - cy) < 0 and (y-cy)**2 < (radius*0.55)**2:
                    r, g, b = 79, 195, 247
                # Center dot
                if dist < 3:
                    r, g, b = 79, 195, 247
            
            row.extend([r, g, b, a])
        pixels.append(bytes(row))
    
    raw_data = b''
    for row in pixels:
        raw_data += b'\x00' + row  # filter byte + row data
    
    # Create PNG
    def chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    idat = zlib.compress(raw_data)
    
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', ihdr)
    png += chunk(b'IDAT', idat)
    png += chunk(b'IEND', b'')
    
    return png

for size in [192, 512]:
    with open(f'/c/Users/cages/task-app/static/icon-{size}.png', 'wb') as f:
        f.write(create_png(size))
    print(f'Created icon-{size}.png')

print('Done')
