import csv
import os
import secrets
import string

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.core.validators import validate_email
from django.db import IntegrityError

User = get_user_model()


class Command(BaseCommand):
    help = "creates student accounts from list in .csv file and add passwords"

    def add_arguments(self, parser):
        parser.add_argument("-f", "--filepath", type=str, help="path to .csv file")

    def handle(self, *args, **kwargs):
        filepath = kwargs["filepath"]

        if not filepath:
            raise Exception("No file path provided.")

        if not filepath.endswith(".csv"):
            raise Exception("Invalid file type. Only .csv files are allowed.")

        if not os.path.exists(filepath):
            raise Exception("File does not exist")

        with (
            open(filepath, newline="", encoding="utf-8") as infile,
            open(
                filepath.replace(".csv", "_output.csv"),
                "w",
                newline="",
                encoding="utf-8",
            ) as outfile,
        ):
            reader = csv.DictReader(infile)
            rows = list(reader)

            # check if data is valid

            # check required columns are present
            required_columns = {"firstname", "lastname", "email", "username"}
            if reader.fieldnames is None:
                raise ValueError("CSV is missing a header row")

            missing = required_columns - set(reader.fieldnames)
            if missing:
                raise ValueError(f"Missing columns in CSV: {missing}")

            # accumulate all errors
            errors: list[str] = []
            for row in rows:
                # email
                try:
                    validate_email(row["email"])
                except ValidationError as e:
                    errors.append(f"{row}: {e}")
                    continue

            if len(errors) > 0:
                print("Errors found in CSV file. Please correct them and try again.")
                print("Errors: ")
                for error in errors:
                    print(error)
                return

            # create users
            # only so that lsp doesnt complain
            if reader.fieldnames is None:
                raise ValueError("CSV must have headers")

            fieldnames = list(reader.fieldnames) + ["password"]
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)

            writer.writeheader()

            for row in rows:
                alphabet = string.ascii_letters + string.digits + "!"

                password = "".join(secrets.choice(alphabet) for _ in range(8))

                try:
                    user = User.objects.create_user(
                        username=row["username"],
                        email=row["email"],
                        first_name=row["firstname"],
                        last_name=row["lastname"],
                        password=password,
                    )
                    writer.writerow(row | {"password": password})

                    print(f"Created user: {user.username}")

                except IntegrityError:
                    print(
                        f"User with overlap already exists {row['username']}. Skipping.."
                    )
