"""Upload demo PDFs from local ex_company/ to server /opt/financial-analyzer/demo_pdfs/."""
import paramiko
import os

LOCAL = r'Y:\claude projects\financial-analyzer\ex_company'
REMOTE = '/opt/financial-analyzer/demo_pdfs'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('43.167.247.182', port=22, username='root', password='REDACTED', timeout=15)

# Create remote directory
stdin, stdout, stderr = client.exec_command('mkdir -p ' + REMOTE)
stdout.channel.recv_exit_status()

sftp = client.open_sftp()
count = 0
for root, dirs, files in os.walk(LOCAL):
    for f in files:
        if not f.endswith('.pdf'):
            continue
        local_path = os.path.join(root, f)
        rel = os.path.relpath(local_path, LOCAL)
        parts = rel.replace(os.sep, '/').split('/')
        # parts: [company_folder, year, filename]
        new_name = parts[0] + '__' + parts[1] + '__' + parts[2]
        remote_path = REMOTE + '/' + new_name
        sftp.put(local_path, remote_path)
        count += 1
        print('uploaded (' + str(count) + '/18): ' + new_name)

sftp.close()
stdin, stdout, stderr = client.exec_command('chown -R financial-analyzer:financial-analyzer ' + REMOTE)
stdout.channel.recv_exit_status()
print('done')
client.close()
