// File Server
import * as fs from 'fs';

export function readUserFile(filename: string): string {
    // VULNERABLE: Path Traversal
    const content = fs.readFileSync(filename, 'utf-8');
    return content;
}

export function serveFile(path: string): Buffer {
    // VULNERABLE: No path validation
    return fs.readFileSync(path);
}
