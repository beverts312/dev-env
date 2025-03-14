alias v='source venv/bin/activate'

function pinit() {
  echo "Initialize virtualenv"
  virtualenv venv

  echo "Activate virtualenv"
  source venv/bin/activate

  echo "Install requirements"
  if [ -f dev-requirements.txt ]; then
      pip install -r dev-requirements.txt
  else
      pip install -r requirements.txt
  fi
}