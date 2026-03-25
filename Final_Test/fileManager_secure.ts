// Secure File Manager
import { spawn } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

export function compressFile(filename: string): Promise<void> {
    // SECURE: Using spawn with argument array (no shell)
    return new Promise((resolve, reject) => {
        const process = spawn('zip', [`${filename}.zip`, filename]);
        
        process.on('close', (code) => {
            if (code === 0) resolve();
            else reject(new Error(`Compression failed with code ${code}`));
        });
    });
}

export function deleteFile(filepath: string): void {
    // SECURE: Using fs module instead of shell command
    const resolvedPath = path.resolve(filepath);
    
    if (!fs.existsSync(resolvedPath)) {
        throw new Error('File not found');
    }
    
    fs.unlinkSync(resolvedPath);
}
