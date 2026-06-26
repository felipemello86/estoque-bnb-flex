#!/bin/bash
pip install -r requirements.txt
python3 -c "from database import init_db; init_db()"
