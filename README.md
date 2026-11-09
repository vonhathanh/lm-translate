# Installation:

1. Install uv
2. Install dependencies: `uv pip install -r requirements.txt`
3. Create .env file from .env.example template, fill all required env variables

# Run server:

`cd server && uvicorn main:app --host 0.0.0.0 --port 5000 --reload`

# migration

Auto generate
migration script according to updated models definition in code:
`alembic revision --autogenerate -m "add raw colun to book"`

Run the migration: `alembic upgrade head`

# Add trigger to Database

Run `alembic revision -m "commit message"` -> write the trigger definition & add trigger to db in the newly created migration file

Run `alembic upgrade head`

# Deployment:

1. Build docker image: `docker build -t lm-translate .`

2. Create a network bridge for the containers if we run postgres, redis in separated docker command:

    `docker network create localnet`

    Note, this can be skipped by using docker compose, just not a fan of it.

3. Run the image by this command: 
    `docker run -d --network localnet --name lm-translate -p 5000:5000 lm-translate`

    Or just using a docker GUI to run the newly built image

# Monitoring:
Run `npx @bull-board/cli -r redis://localhost:6379`
