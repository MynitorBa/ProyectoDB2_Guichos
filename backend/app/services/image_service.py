from pathlib import Path

from fastapi import HTTPException, UploadFile


ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
EXT_MIME = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.png': 'image/png', '.webp': 'image/webp', '.gif': 'image/gif',
}


async def read_valid_image(file: UploadFile) -> tuple[bytes, str]:
    ext = Path(file.filename or '').suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f'Tipo no permitido. Usa: {", ".join(sorted(ALLOWED_EXTENSIONS))}',
        )
    content = await file.read(MAX_IMAGE_BYTES + 1)
    if not content:
        raise HTTPException(400, 'La imagen está vacía.')
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(413, 'La imagen supera el límite de 5 MB.')
    signatures = {
        '.jpg': (b'\xff\xd8\xff',), '.jpeg': (b'\xff\xd8\xff',),
        '.png': (b'\x89PNG\r\n\x1a\n',),
        '.gif': (b'GIF87a', b'GIF89a'), '.webp': (b'RIFF',),
    }
    if not any(content.startswith(signature) for signature in signatures[ext]):
        raise HTTPException(400, 'El contenido no coincide con el tipo de imagen.')
    if ext == '.webp' and content[8:12] != b'WEBP':
        raise HTTPException(400, 'El archivo WEBP no es válido.')
    return content, EXT_MIME[ext]
