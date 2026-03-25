// Secure File Server
import * as fs from 'fs';
import * as path from 'path';

const ALLOWED_DIR = path.resolve('/var/app/user_files');

export function readUserFile(filename: string): string {
    // SECURE: Path traversal protection
    const requestedPath = path.resolve(ALLOWED_DIR, filename);
    
    if (!requestedPath.startsWith(ALLOWED_DIR)) {
        throw new Error('Path traversal attempt detected');
    }
    
    if (!fs.existsSync(requestedPath)) {
        throw new Error('File not found');
    }
    
    return fs.readFileSync(requestedPath, 'utf-8');
}

export function serveFile(filepath: string): Buffer {
    // SECURE: Path validation
    const requestedPath = path.resolve(ALLOWED_DIR, filepath);
    
    if (!requestedPath.startsWith(ALLOWED_DIR)) {
        throw new Error('Invalid file path');
    }
    
    return fs.readFileSync(requestedPath);
}
