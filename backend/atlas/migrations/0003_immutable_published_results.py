from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("""
            CREATE FUNCTION atlas_immutable_result() RETURNS trigger AS $$
            BEGIN
              IF OLD.status = 'complete' AND (
                NEW.result IS DISTINCT FROM OLD.result OR
                NEW.frame_data IS DISTINCT FROM OLD.frame_data OR
                NEW.status IS DISTINCT FROM OLD.status
              ) THEN RAISE EXCEPTION 'Published analysis results are immutable'; END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        schema_editor.execute("""
            CREATE TRIGGER atlas_result_immutable BEFORE UPDATE ON atlas_analysissnapshot
            FOR EACH ROW EXECUTE FUNCTION atlas_immutable_result();
        """)


def remove(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("""
            DROP TRIGGER IF EXISTS atlas_result_immutable ON atlas_analysissnapshot;
        """)
        schema_editor.execute("DROP FUNCTION IF EXISTS atlas_immutable_result();")


class Migration(migrations.Migration):
    dependencies = [("atlas", "0002_assessmentrequestwindow_providerrequestbudget")]
    operations = [migrations.RunPython(install, remove)]
