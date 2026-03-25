// File Manager
import { exec } from 'child_process';

export function compressFile(filename: string): void {
    // VULNERABLE: Command Injection
    exec(`zip ${filename}.zip ${filename}`, (error, stdout, stderr) => {
        if (error) console.error(error);
    });
}

export function deleteFile(filepath: string): void {
    // VULNERABLE: Command Injection
    exec(`rm -rf ${filepath}`);
}
