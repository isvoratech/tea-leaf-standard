#!/usr/bin/env bash
# READ-ONLY check of the VPS: finds Field Diary + Fertilizer app, ports, DB, Apache rules.
# Run as root:  bash deploy/discover.sh | tee /root/leaf_standard_discover.txt
set -u
hr(){ printf '\n==== %s ====\n' "$1"; }

hr "Host"
hostname; cat /etc/redhat-release 2>/dev/null; date

hr "Field Diary folders"
find /var/www /home /opt /root -maxdepth 4 -type d \( -iname '*field*diary*' -o -iname 'field_diary*' \) 2>/dev/null | head -20

hr "Fertilizer app folders"
find /var/www /home /opt /root -maxdepth 4 -type d -iname '*fertili*' 2>/dev/null | head -20

hr "systemd services (field / fert / saduai)"
systemctl list-units --type=service --all --no-pager 2>/dev/null | grep -Ei 'field|diary|fert|saduai|uvicorn|gunicorn' || echo none
for s in $(systemctl list-units --type=service --all --no-legend 2>/dev/null | awk '{print $1}' | grep -Ei 'field|diary|fert'); do
  echo "--- $s"; systemctl cat "$s" 2>/dev/null | grep -E 'WorkingDirectory|ExecStart|EnvironmentFile|User='
done

hr "Listening ports 8000-8099"
ss -ltnp 2>/dev/null | awk 'NR==1 || $4 ~ /:80[0-9][0-9]$/'
echo; echo "8015 free?"; ss -ltn | grep -q ':8015 ' && echo "NO - in use" || echo "yes"

hr "Apache proxy rules"
grep -RhnE 'ProxyPass(Match)?|Include' /etc/apache2/conf.d/userdata 2>/dev/null | grep -Ei 'field|diary|fert|80[0-9][0-9]' | head -40
ls -R /etc/apache2/conf.d/userdata 2>/dev/null | head -40

hr "Field Diary DB"
su - postgres -c "psql -Atc \"select datname from pg_database where datname ilike '%field%' or datname ilike '%fert%'\"" 2>/dev/null
su - postgres -c "psql -d field_diary -Atc '\dt'" 2>/dev/null | head -40
for d in $(find /var/www /home /opt -maxdepth 5 -name '.env' -path '*field*' 2>/dev/null); do
  echo "--- $d"; grep -Ei 'DATABASE|DB_' "$d" | sed -E 's#(://[^:]+:)[^@]+@#\1****@#'
done

hr "Field Diary front-end (for adding a menu link)"
for d in $(find /var/www /home /opt -maxdepth 4 -type d -iname '*field*diary*' 2>/dev/null); do
  find "$d" -maxdepth 4 \( -name 'index.html' -o -name 'main.py' -o -name 'App.jsx' -o -name 'App.tsx' -o -name 'package.json' \) -not -path '*/node_modules/*' 2>/dev/null | head
done

hr "pg_hba guard"
ls -l /root/fix-pg-hba.sh 2>/dev/null; crontab -l 2>/dev/null | grep -i hba

hr "Python"
python3.11 --version 2>/dev/null; python3 --version
echo; echo "Done. Send this output back if anything looks unusual."
