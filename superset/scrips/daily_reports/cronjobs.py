#cron jobs for CT Daily Reports

# BMI
7 7 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [BMI]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'BMI' >> /path/to/scripts/ct_subscribers.log 2>&1

# FFMC
11 9 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RENOVO FFMC]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'RENOVO FFMC' >> /path/to/scripts/ct_subscribers.log 2>&1

# HRCH
20 10 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RENOVO HRCH]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'RENOVO HRCH' >> /path/to/scripts/ct_subscribers.log 2>&1

# LLCH
35 10 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RENOVO LLCH]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'RENOVO LLCH' >> /path/to/scripts/ct_subscribers.log 2>&1

# GEHC
30 10 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [GEHC]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'GEHC' >> /path/to/scripts/ct_subscribers.log 2>&1

# WVUM
0 12 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [WVUM]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'WVUM' >> /path/to/scripts/ct_subscribers.log 2>&1

# NYP
5 12 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [NYP]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'NYP' >> /path/to/scripts/ct_subscribers.log 2>&1

# MUHS
15 12 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [MUHS]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'MUHS' >> /path/to/scripts/ct_subscribers.log 2>&1

# NGHS
10 12 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [NGHS]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'NGHS' >> /path/to/scripts/ct_subscribers.log 2>&1

# RDNT
52 11 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RDNT]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'RDNT' >> /path/to/scripts/ct_subscribers.log 2>&1

# RESPAMC
55 13 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RES PAMC]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'RES PAMC' >> /path/to/scripts/ct_subscribers.log 2>&1

# IMGPAR
50 13 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RES IMGPAR]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'RES IMGPAR' >> /path/to/scripts/ct_subscribers.log 2>&1

# mmh
10 14 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [mmh]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'mmh' >> /path/to/scripts/ct_subscribers.log 2>&1

# SHC
25 15 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [SHC]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'SHC' >> /path/to/scripts/ct_subscribers.log 2>&1

# Sodexonchs
30 14 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [SODEXO NCHS]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'SODEXO NCHS' >> /path/to/scripts/ct_subscribers.log 2>&1

# HRHS
5 15 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [HRHS]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'HRHS' >> /path/to/scripts/ct_subscribers.log 2>&1

# RSMC
19 14 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RES RSMC]" >> /path/to/scripts/ct_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/ct_subscribers.py 'RES RSMC' >> /path/to/scripts/ct_subscribers.log 2>&1


#MR DAILY REPORT JOBS

10 12 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [MUHS]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'MUHS' >> /path/to/scripts/mr_subscribers.log 2>&1


52 13 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RES PAMC]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'PAMC' >> /path/to/scripts/mr_subscribers.log 2>&1


06 07 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [BMI]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'BMI' >> /path/to/scripts/mr_subscribers.log 2>&1


07 12 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [NYP]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'NYP' >> /path/to/scripts/mr_subscribers.log 2>&1


22 14 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [SHC]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'SHC' >> /path/to/scripts/mr_subscribers.log 2>&1


00 14 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [traimg]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'TRAIMG' >> /path/to/scripts/mr_subscribers.log 2>&1


12 14 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [SODEXO NCHS]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'SODEXO NCHS' >> /path/to/scripts/mr_subscribers.log 2>&1


05 14 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [NHRMC]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'NHRMC' >> /path/to/scripts/mr_subscribers.log 2>&1


10 14 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RES OSNC]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'OSNC' >> /path/to/scripts/mr_subscribers.log 2>&1


55 01 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RES EHMC]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'EHMC' >> /path/to/scripts/mr_subscribers.log 2>&1


10 15 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [HRHS]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'HRHS' >> /path/to/scripts/mr_subscribers.log 2>&1


45 13 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RES IMGPAR]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'IMGPAR' >> /path/to/scripts/mr_subscribers.log 2>&1


32 13 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RES SDIM]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'SDIM' >> /path/to/scripts/mr_subscribers.log 2>&1


15 12 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [NGHS]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'NGHS' >> /path/to/scripts/mr_subscribers.log 2>&1


48 13 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RES CCHS]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'CCHS' >> /path/to/scripts/mr_subscribers.log 2>&1


01 14 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RES LLMC]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'LLMC' >> /path/to/scripts/mr_subscribers.log 2>&1


18 14 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RES RSMC]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'RSMC' >> /path/to/scripts/mr_subscribers.log 2>&1


42 11 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [RDNT]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'RDNT' >> /path/to/scripts/mr_subscribers.log 2>&1


35 10 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [GEHC]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'GEHC' >> /path/to/scripts/mr_subscribers.log 2>&1


00 12 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [WVUM]" >> /path/to/scripts/mr_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/mr_subscribers.py 'WVUM' >> /path/to/scripts/mr_subscribers.log 2>&1


#cron job for Cathlab Daily Reports

# MUHS Cathlab
10 12 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [MUHS]" >> /path/to/scripts/cathlab_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/cathlab_subscribers.py 'MUHS' >> /path/to/scripts/cathlab_subscribers.log 2>&1

# GEHC Cathlab
40 10 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [GEHC]" >> /path/to/scripts/cathlab_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/cathlab_subscribers.py 'GEHC' >> /path/to/scripts/cathlab_subscribers.log 2>&1

# WVUM Cathlab
1 12 * * * echo "$(date '+\%Y-\%m-\%d \%H:\%M:\%S') [WVUM]" >> /path/to/scripts/cathlab_subscribers.log 2>&1 && /usr/bin/python3 /path/to/scripts/cathlab_subscribers.py 'WVUM' >> /path/to/scripts/cathlab_subscribers.log 2>&1

