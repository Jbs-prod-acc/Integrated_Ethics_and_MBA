from app_support import *


def _normalize_sampling_size_list(sample_sizes):
    cleaned_sizes = []

    for index, raw_value in enumerate(sample_sizes, start=1):
        value = str(raw_value or '').strip()
        if not value:
            cleaned_sizes.append('')
            continue

        compact_value = value.replace(' ', '')
        if compact_value.isdigit():
            if int(compact_value) < 1:
                return None, f"Sampling size row {index} must be a positive number."
            cleaned_sizes.append(compact_value)
            continue

        parts = compact_value.split('-')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            start_value = int(parts[0])
            end_value = int(parts[1])

            if start_value < 1 or end_value < 1:
                return None, f"Sampling size row {index} must use positive numbers only."
            if end_value < start_value:
                return None, f"Sampling size row {index} must use an interval like 100-150 where the second number is not smaller than the first."
            if end_value > (start_value * 2):
                return None, f"Sampling size row {index} is invalid: in an interval like 100-n, n cannot be more than twice the first number."

            cleaned_sizes.append(f"{start_value}-{end_value}")
            continue

        return None, f"Sampling size row {index} must be a single number like 100 or an interval like 100-150."

    return cleaned_sizes, None

@app.route('/form_a_sec1', methods=['GET', 'POST'])
def form_a_sec1 ():

    sup_list = getSupervisorsList()

    try:
        if request.method == 'POST':
            # Verify user is logged in
            user_id = session.get('id')
            if not user_id:
                return jsonify({'error': 'Unauthorized'}), 401

            # Check if user already submitted other forms
            formB = db_session.query(FormB).options(
                defer(FormB.permission_letter),
                defer(FormB.prior_clearance),
                defer(FormB.ethics_evidence),
                defer(FormB.proposal_path),
                defer(FormB.pending_note),
                defer(FormB.private_permission_file)
            ).filter_by(user_id=user_id).first()
            if formB:
                flash("You are not permitted to fill this form", "warning")
                return redirect(url_for("student_dashboard"))

            formC = db_session.query(FormC).filter_by(user_id=user_id).first()
            if formC:
                flash("You are not permitted to fill this form", "warning")
                return redirect(url_for("student_dashboard"))

            # Get form data
            form_data = request.form
            user = db_session.query(User).filter(User.user_id == user_id).first()
            if not user:
                flash("User not found. Please log in again.", "danger")
                return redirect(url_for("login"))

            supervisor = db_session.query(User).filter(User.user_id == user.supervisor_id).first()
            if not supervisor:
                flash("Supervisor not found. Please contact admin.", "danger")
                return redirect(url_for("student_dashboard"))

            form_requirements = db_session.query(FormARequirements).filter(FormARequirements.user_id == user_id).first()
            if not form_requirements:
                flash("Form A requirements not found. Please complete them first.", "warning")
                return redirect(url_for("student_dashboard"))

            # Create or update record
            form, error_response = _get_or_create_forma_draft(user_id, form_data)
            if error_response:
                return error_response

            form.attachment_id = form_requirements.id
            _apply_forma_autosave_payload(form, form_data, section='sec1', include_declaration=False)
            form.email = user.email
            form.supervisor = supervisor.full_name
            form.supervisor_email = supervisor.email

            db_session.add(form)
            db_session.commit()
            flash("Form submitted successfully.", "success")
            return redirect(url_for("form_a_sec2"))

        # GET request: always load/create a single active draft for autosave.
        current_user_id = session.get('id')
        form_data, error_response = _get_or_create_forma_draft(current_user_id, {})
        if error_response:
            return error_response
        db_session.commit()
        return render_template('form-a-section1.html', supervisors=sup_list, form_data=form_data)

    except Exception as e:
        db_session.rollback()
        print(f"⚠️ Error in form_a_section1: {str(e)}")  # Optional: use logging
        flash("An unexpected error occurred while submitting the form. Please try again.", "danger")
        return redirect(url_for("student_dashboard"))

    finally:
        db_session.close()

   
@app.route('/submit_form_a_sec1', methods=['GET', 'POST'])
def submit_form_a_sec1():
    try:
        # Ensure user is logged in
        user_id = session.get('id')
        if not user_id:
            flash("You must be logged in to submit this form.", "warning")
            return redirect(url_for("login"))

        # Ensure attachments are set
        attachment_id = session.get('formA-attachments_id')
        if not attachment_id:
            flash("Attachment information is missing. Please upload attachments first.", "warning")
            return redirect(url_for("form_a_sec1"))

        # Reuse the active draft when present; create only if no draft exists.
        formA_record, error_response = _get_or_create_forma_draft(user_id, request.form)
        if error_response:
            return error_response

        formA_record.user_id = user_id
        formA_record.attachment_id = attachment_id
        for key, value in request.form.items():
            if key in {'csrf_token', 'forma_id'}:
                continue
            if hasattr(FormA, key):
                setattr(formA_record, key, value)

        db_session.add(formA_record)
        db_session.commit()

        flash("Form A (Section 1) submitted successfully!", "success")
        return redirect(url_for("form_a_sec2"))

    except KeyError as ke:
        db_session.rollback()
        flash(f"Missing required field: {ke}", "danger")
        print(f"⚠️ Missing key in form submission: {ke}")
        return redirect(url_for("form_a_sec1"))

    except Exception as e:
        db_session.rollback()
        flash("An unexpected error occurred while submitting your form. Please try again.", "danger")
        print(f"⚠️ Error in /submit_form_a_sec1: {str(e)}")

        return redirect(url_for("form_a_sec1"))

    finally:
        db_session.close()


# ---------------- Section 2 ------------------
@app.route('/form_a_sec2', methods=['GET', 'POST'])
def form_a_sec2():
    try:
        data = request.form
        if request.method == 'POST':
            def to_bool(val):
                if isinstance(val, bool):
                    return val
                if val in [None, '']:
                    return False
                return str(val).lower() in ['yes', 'true', '1', 'on', 'checked']

            # ✅ Ensure user session exists
            user_id = session.get('id')
            if not user_id:
                flash("You must be logged in to fill this form.", "warning")
                return redirect(url_for("login"))

            # ✅ Check if the user already filled other forms
            formB = db_session.query(FormB).options(
                defer(FormB.permission_letter),
                defer(FormB.prior_clearance),
                defer(FormB.ethics_evidence),
                defer(FormB.proposal_path),
                defer(FormB.pending_note),
                defer(FormB.private_permission_file)
            ).filter_by(user_id=user_id).first()
            if formB:
                flash("You are not permitted to fill this form", "warning")
                return redirect(url_for("student_dashboard"))

            formC = db_session.query(FormC).filter_by(user_id=user_id).first()
            if formC:
                flash("You are not permitted to fill this form", "warning")
                return redirect(url_for("student_dashboard"))

            # ✅ Fetch the existing Form A record
            form = _get_latest_forma_for_user(user_id)
            if not form:
                flash("No existing Form A record found for this user.", "danger")
                return redirect(url_for("form_a_section1"))

            _apply_forma_autosave_payload(form, data, section='sec2', include_declaration=False)

            # ✅ Commit to DB
            db_session.add(form)
            db_session.commit()

            flash("Form A Section 2 submitted successfully.", "success")
            return redirect(url_for("form_a_sec3"))

        # GET method fallback - preload existing values for checkbox/text persistence
        user_id = session.get('id')
        form_data = _get_latest_forma_for_user(user_id)
        return render_template('form-a-section2.html', form_data=form_data)

    except KeyError as ke:
        db_session.rollback()
        flash(f"Missing required session or field: {ke}", "danger")
        print(f"⚠️ Missing key in /form_a_sec2: {ke}")
        return redirect(url_for("form_a_section2"))

    except Exception as e:
        db_session.rollback()
        flash("An unexpected error occurred while submitting Form A Section 2. Please try again.", "danger")
        print(f"⚠️ Error in /form_a_sec2: {str(e)}")
        return redirect(url_for("form_a_section2"))

    finally:
        db_session.close()

@app.route('/submit_form_a_sec2', methods=['GET', 'POST'])
def submit_form_a_sec2():
    try:
        if request.method == 'POST':
            user_id = session.get('id')
            if not user_id:
                flash("Unauthorized access. Please log in to continue.", "warning")
                return redirect(url_for("login"))

            form_record = _get_latest_forma_for_user(user_id)
            if not form_record:
                flash("No existing Form A record found for this user.", "danger")
                return redirect(url_for("form_a_section1"))

            data = _build_autosave_data(request.form)

            bool_fields = [
                'survey', 'focus_groups', 'observations', 'interviews', 'documents',
                'vulnerable_communities', 'age_range', 'uj_employees', 'vulnerable',
                'non_english', 'own_students', 'poverty', 'no_education',
                'disclosure', 'discomfiture', 'deception',
                'sensitive', 'prejudice', 'intrusive_techniques', 'illegal_activities',
                'personal', 'available_records', 'inventories', 'risk_activities',
                'incentives', 'financial_costs', 'reward', 'conflict',
                'uj_premises', 'uj_facilities', 'uj_funding'
            ]

            for field in bool_fields:
                setattr(form_record, field, _autosave_str_to_bool(data[field]) if field in data else False)

            form_record.assessment_other_specify = request.form.get('assessment_other_specify', '')
            form_record.vulnerable_other_specify = request.form.get('vulnerable_other_specify', '')
            form_record.activity_specify = request.form.get('activity_specify', '')
            form_record.vulnerable_comments_1 = request.form.get('vulnerable_comments_1', '')
            form_record.vulnerable_comments_2 = request.form.get('vulnerable_comments_2', '')
            form_record.vulnerable_comments_3 = request.form.get('vulnerable_comments_3', '')
            form_record.risk_rating = request.form.get('risk_rating', '')
            form_record.risk_justification = request.form.get('risk_justification', '')
            form_record.benefits_description = request.form.get('benefits_description', '')
            form_record.risk_mitigation = request.form.get('risk_mitigation', '')
            form_record.apply_comments = request.form.get('apply_comments', '')
            form_record.other_sec2 = request.form.get('other_sec2', '')

            form_record.interviews_one = _autosave_str_to_bool(data.get('interviews')) if 'interviews' in data else False
            form_record.documents_one = _autosave_str_to_bool(data.get('documents')) if 'documents' in data else False

            db_session.commit()
            flash("Form A Section 2 submitted successfully!", "success")
            return redirect(url_for("form_a_sec3"))

        user_id = session.get('id')
        form_data = _get_latest_forma_for_user(user_id)
        return render_template('form-a-section2.html', form_data=form_data)

    except KeyError as ke:
        db_session.rollback()
        flash(f"Missing required data: {ke}", "danger")
        print(f"⚠️ KeyError in /submit_form_a_sec2: {ke}")
        return redirect(url_for("form_a_section2"))

    except Exception as e:
        db_session.rollback()
        flash("An unexpected error occurred while submitting the form. Please try again.", "danger")
        print(f"⚠️ Exception in /submit_form_a_sec2: {e}")
        return redirect(url_for("form_a_section2"))

    finally:
        db_session.close()

# ---------------- Section 3 ------------------
@app.route('/form_a_sec3', methods=['GET', 'POST'])
def form_a_sec3():
    try:
        if request.method == 'POST':
            data = request.form
            def to_yes_no(val):
                if isinstance(val, bool):
                    return 'Yes' if val else 'No'
                if val in [None, '']:
                    return ''
                return 'Yes' if str(val).lower() in ['yes', 'true', '1', 'on', 'checked'] else 'No'

            user_id = session.get('id')

            # ✅ Check user authentication
            if not user_id:
                flash("Unauthorized access. Please log in to continue.", "warning")
                return redirect(url_for("login"))

            # ✅ Retrieve existing Form A record
            form = _get_latest_forma_for_user(user_id)
            if not form:
                flash("No existing Form A record found for this user.", "danger")
                return redirect(url_for("form_a_section1"))

            _apply_forma_autosave_payload(form, data, section='sec3', include_declaration=False)

            # ✅ Save updates
            db_session.add(form)
            db_session.commit()

            flash("Form A Section 3 submitted successfully!", "success")
            return redirect(url_for("form_a_sec4"))

        # ✅ Handle GET request
        user_id = session.get('id')
        form_data = _get_latest_forma_for_user(user_id)
        return render_template('form-a-section3.html', form_data=form_data)

    except KeyError as ke:
        db_session.rollback()
        flash(f"Missing field or session key: {ke}", "danger")
        print(f"⚠️ KeyError in /form_a_sec3: {ke}")
        return redirect(url_for("form_a_sec3"))

    except Exception as e:
        db_session.rollback()
        flash("An unexpected error occurred while submitting Form A Section 3. Please try again.", "danger")
        print(f"⚠️ Exception in /form_a_sec3: {e}")
        return redirect(url_for("form_a_sec3"))

    finally:
        db_session.close()

@app.route('/form_a_upload', methods=['GET'])
def form_a_upload ():
    return render_template('form-a-upload.html')


###
###
### this is the function to focus on when intergrating MBA and Ethics
###
@app.route('/back_end/monitor', methods=['GET'])
def monitor ():
    id=session.get('id')
    user_profile=db_session.query(User).filter_by(user_id=id).first()
    all_users=db_session.query(User).filter(User.role=="STUDENT").all()
    users_list = []
    for user in all_users:
        users_list.append({
            "user_id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role.value,
        })

    role=user_profile.role.value
    
    return render_template('monitor.html',role=role,users_list=users_list)

@app.route('/back_end/monitor_forms/view_forms/<string:user_id>', methods=['GET','POST'])
def monitor_forms (user_id):
    id=session.get('id')
    user_profile=db_session.query(User).filter_by(user_id=id).first()
    form = None
    all_users=db_session.query(User).filter(User.role=="STUDENT").all()
    for model in [FormA, FormB, FormC]:
        form = db_session.query(model).filter_by(user_id=user_id).all()
        if form:
            break  # Stop once the form is found
    users_list = []
    for user in all_users:
        users_list.append({
            "user_id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role.value,
        })
    if request.method=="POST":
        for items in form:

            db_session.delete(items)
            db_session.commit()
            msg = "User deleted successfully"
            return redirect(url_for('monitor', messages=[msg]))
    
   
    role=user_profile.role.value
    return render_template('monitor.html',role=role,users_list=users_list,form=form)

# ---------------- Section 4 ------------------
@app.route('/form_a_sec4', methods=['GET', 'POST'])
def form_a_sec4():
    if request.method == 'POST':
        try:
            def to_bool(val):
                if isinstance(val, bool):
                    return val
                if val in [None, '']:
                    return False
                return str(val).lower() in ['yes', 'true', '1', 'on', 'checked']

            user_id = session.get('id')
            if not user_id:
                return "Unauthorized access. Please log in.", 401

            # --- Fetch the existing FormA record ---
            form = _get_latest_forma_for_user(user_id)
            if not form:
                return "No existing Form A record found for this user.", 404

            _apply_forma_autosave_payload(form, request.form, section='sec4', include_declaration=False)

            # --- Handle File Upload ---
            file = request.files.get('private_permission_file')
            if file and file.filename:
                form.private_permission_file = file.read()
                form.private_permission_filename = file.filename

            # --- Commit to Database ---
            db_session.commit()

            flash("Form A Section 4 submitted successfully.", "success")
            return redirect(url_for("form_a_sec5"))

        except SQLAlchemyError as e:
            db_session.rollback()
            print("Database Error:", e)
            traceback.print_exc()
            return render_template('form-a-section4.html', messages=["Database error occurred. Please try again."])

        except Exception as e:
            db_session.rollback()
            print("Unexpected Error:", e)
            traceback.print_exc()
            return render_template('form-a-section4.html', messages=["An unexpected error occurred. Please try again."])

    # If GET request → render Section 4 with existing values
    user_id = session.get('id')
    form_data = _get_latest_forma_for_user(user_id)
    return render_template('form-a-section4.html', form_data=form_data)
@app.route('/submit_form_a_sec4', methods=['GET', 'POST'])
def submit_form_a_sec4 ():
    try:
        if request.method == 'POST':
            user_id = session.get('id')
            if not user_id:
                return "Unauthorized access. Please log in.", 401

            form = _get_latest_forma_for_user(user_id)
            if not form:
                return "No existing Form A record found for this user.", 404

            data = _build_autosave_data(request.form)

            form.quantitative = _autosave_str_to_bool(data.get('quantitative')) if 'quantitative' in data else False
            form.qualitative = _autosave_str_to_bool(data.get('qualitative')) if 'qualitative' in data else False
            form.mixed_methods = _autosave_str_to_bool(data.get('mixed_methods')) if 'mixed_methods' in data else False
            form.paradigm_explanation = request.form.get('paradigm_explanation', '')
            form.design = request.form.get('design', '')
            form.participants_description = request.form.get('participants_description', '')
            form.population = data.get('population', '')
            form.sampling_method = data.get('sampling_method', '')
            form.sampling_size = data.get('sample_size', '')
            form.inclusion_criteria = data.get('inclusion_criteria', '')
            form.duration_timing = request.form.get('duration_timing', '')
            form.contact_details_method = request.form.get('contact_details_method', '')
            form.conflict_interest = _autosave_str_to_bool(data.get('conflict_interest')) if 'conflict_interest' in data else False
            form.conflict_explanation = request.form.get('conflict_explanation', '')

            form.data_methods = data.get('data_methods', '')
            form.questionnaire_type = request.form.get('questionnaire_type', '')
            questionnaire_permission = request.form.get('questionnaire_permission', '')
            if questionnaire_permission == 'Yes':
                form.permission_obtained = 'Yes'
                form.open_source = 'No'
            elif questionnaire_permission == 'Open Source':
                form.permission_obtained = 'No'
                form.open_source = 'Yes'
            else:
                form.permission_obtained = None
                form.open_source = None
            form.interview_type = request.form.get('interview_type', '')
            form.interview_recording = request.form.get('interview_recording', '')
            selected_methods = [method.strip() for method in form.data_methods.split(',') if method.strip()]
            form.use_focus_groups = 'focus' in selected_methods
            form.focus_recording = request.form.get('focus_recording', '')
            form.observation_details = request.form.get('observation_details', '')
            form.documents_details = request.form.get('documents_details', '')
            form.other_details = request.form.get('other_details', '')
            form.data_collection_procedure = request.form.get('data_collection_procedure', '')
            form.data_collectors = request.form.get('data_collectors', '')
            form.intervention = _autosave_str_to_bool(data.get('intervention')) if 'intervention' in data else False
            form.intervention_details = request.form.get('intervention_details', '')
            form.sensitive_data = request.form.get('sensitive_data', '')
            form.translator = _autosave_str_to_bool(data.get('translator')) if 'translator' in data else False
            form.translator_procedure = request.form.get('translator_procedure', '')
            form.instrument_attachment_reason = request.form.get('instrument_attachment_reason', '')

            secondary_data = data.get('uses_secondary_data', data.get('secondary_data', ''))
            form.uses_secondary_data = _autosave_str_to_bool(secondary_data) if secondary_data is not None else False

            shared_fields = [
                'data_nature', 'data_origin', 'access_conditions', 'personal_info',
                'personal_info_comment', 'data_anonymized', 'anonymization_comment',
                'permission_details', 'public_data_description', 'shortcomings_reported',
                'limitations_reporting', 'methodology_alignment', 'data_acknowledgment'
            ]
            for field in shared_fields:
                if hasattr(form, field):
                    setattr(form, field, request.form.get(field, ''))

            if form.uses_secondary_data:
                form.secondary_data_type = request.form.get('data_type', '')
                if form.secondary_data_type in ['public','private', 'both']:
                    private_permission_value = request.form.get('privatePermission', request.form.get('private_permission'))
                    form.private_permission = 'Yes' if _autosave_str_to_bool(private_permission_value) else 'No'
                else:
                    form.private_permission = ''
            else:
                form.secondary_data_type = ''
                form.private_permission = ''

            file = request.files.get('private_permission_file')
            if file and file.filename:
                form.private_permission_file = file.read()
                form.private_permission_filename = file.filename

            db_session.commit()
            flash("Form A Section 4 submitted successfully.", "success")
            return redirect(url_for("form_a_sec5"))

        user_id = session.get('id')
        form_data = _get_latest_forma_for_user(user_id)
        return render_template('form-a-section4.html', form_data=form_data)

    except Exception as e:
        db_session.rollback()
        print(f"⚠️ Exception in /submit_form_a_sec4: {e}")
        return render_template('form-a-section4.html', messages=["An unexpected error occurred. Please try again."])

# ---------------- Section 5 ------------------
@app.route('/form_a_sec5', methods=['GET', 'POST'])
def form_a_sec5 ():
    if request.method == 'POST':
        def to_bool(val):
            if isinstance(val, bool):
                return val
            if val in [None, '']:
                return False
            return str(val).lower() in ['yes', 'true', '1', 'on', 'checked']

        user_id = session.get('id')
        

        if not user_id:
            return "Unauthorized access. Please log in.", 401

        # Fetch existing form entry for the user
        form = _get_latest_forma_for_user(user_id)
        if not form:
            return "No existing Form A record found for this user.", 404

        cleaned_sample_sizes, sample_size_error = _normalize_sampling_size_list(request.form.getlist('sample_size[]'))
        if sample_size_error:
            flash(sample_size_error, "danger")
            return redirect(url_for("form_a_sec5"))

        _apply_forma_autosave_payload(form, request.form, section='sec5', include_declaration=False)
        form.sampling_size = ','.join(cleaned_sample_sizes)
    
        db_session.add(form)
        db_session.commit()
        return redirect(url_for("form_a_sec6"))
        

    user_id = session.get('id')
    form_data = _get_latest_forma_for_user(user_id)
    return render_template('form-a-section5.html', form_data=form_data)

@app.route('/submit_form_a_sec5', methods=['GET', 'POST'])
def submit_form_a_sec5 ():
    try:
        if request.method == 'POST':
            user_id = session.get('id')
            if not user_id:
                return "Unauthorized access. Please log in.", 401

            form = _get_latest_forma_for_user(user_id)
            if not form:
                return "No existing Form A record found for this user.", 404

            data = _build_autosave_data(request.form)

            form.informed_consent = request.form.get('informed_consent', '')
            form.data_storage = data.get('data_storage', '')
            form.study_benefits = request.form.get('study_benefits', '')
            form.participant_risks = request.form.get('participant_risks', '')
            form.adverse_steps = request.form.get('adverse_steps', '')
            form.community_participation = request.form.get('community_participation', '')
            form.community_effects = request.form.get('community_effects', '')
            form.privacy = data.get('privacy', '')

            for key in ['a','b','c','d','e','f','g','h','i','j','k','l','m','n','o','p','q','r','s']:
                field_name = f'q6_9{key}'
                if hasattr(form, field_name):
                    setattr(form, field_name, _autosave_str_to_bool(data.get(field_name)) if field_name in data else False)

            form.results_feedback = request.form.get('results_feedback', '')
            form.products_access = request.form.get('products_access', '')
            form.publication_plans = request.form.get('publication_plans', '')
            form.participant_comp = request.form.get('participant_comp', '')
            form.participant_costs = request.form.get('participant_costs', '')
            form.ethics_reporting = request.form.get('ethics_reporting', '')

            db_session.commit()
            return redirect(url_for("form_a_sec6"))

        user_id = session.get('id')
        form_data = _get_latest_forma_for_user(user_id)
        return render_template('form-a-section5.html', form_data=form_data)

    except Exception as e:
        db_session.rollback()
        print(f"⚠️ Exception in /submit_form_a_sec5: {e}")
        return render_template('form-a-section5.html')

# ---------------- Section 6 ------------------
@app.route('/form_a_sec6', methods=['GET', 'POST'])
def form_a_sec6():
    if request.method == 'POST':
        try:
            # --- Check user session ---
            user_id = session.get('id')
            if not user_id:
                return "Unauthorized access. Please log in.", 401

            # --- Fetch form and user records ---
            form = _get_latest_forma_for_user(user_id)
            user = db_session.query(User).filter_by(user_id=user_id).first()

            if not form:
                return "No existing Form A record found for this user.", 404

            # --- Update Declaration Section ---
            form.submitted_at = datetime.now()
            form.declaration_name = request.form.get('declaration_name')
            form.applicant_signature = request.form.get('applicant_signature')

            # --- Validate and assign date ---
            date_str = request.form.get('declaration_date')
            try:
                form.declaration_date = datetime.strptime(date_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                return "Invalid date format. Please use YYYY-MM-DD.", 400

            # --- Commit to database ---
            db_session.add(form)
            db_session.commit()

            # --- Try sending confirmation email ---
            try:
                message = f"{form.declaration_name or 'Applicant'} has submitted Form A for review."
                send_email(app, mail, message, [form.supervisor_email])
            except Exception as e:
                app.logger.error(f"⚠️ Failed to send email to {form.supervisor_email}: {e}")
                traceback.print_exc()

            flash("✅ Form A submitted successfully.", "success")
            return redirect(url_for('student_dashboard'))

        except SQLAlchemyError as e:
            db_session.rollback()
            app.logger.error(f"Database error during Form A submission: {e}")
            traceback.print_exc()
            flash("❌ Database error occurred. Please try again.", "danger")
            return render_template('form-a-section6.html')

        except Exception as e:
            db_session.rollback()
            app.logger.error(f"Unexpected error in Form A submission: {e}")
            traceback.print_exc()
            flash("⚠️ An unexpected error occurred. Please try again.", "danger")
            return render_template('form-a-section6.html')

    # GET request → Render the section
    user_id = session.get('id')
    form_data = _get_latest_forma_for_user(user_id)
    return render_template('form-a-section6.html', form_data=form_data)



@app.route('/submit_form_a_sec6', methods=['GET', 'POST'])
def submit_form_a_sec6():
    # This route is handled by form_a_sec6 function above
    # Redirect to avoid duplicate handling
    return redirect(url_for('form_a_sec6'))




# FORM B =====================================================================================================
@app.route('/api/form-b/<form_id>', methods=['GET'])
@login_required
def get_form_b(form_id):
    form_b = db_session.query(FormB).options(
        defer(FormB.permission_letter),
        defer(FormB.prior_clearance),
        defer(FormB.ethics_evidence),
        defer(FormB.proposal_path),
        defer(FormB.pending_note),
        defer(FormB.private_permission_file)
    ).filter_by(form_id=form_id).first()
    if not form_b:
        return jsonify({"message": "Form not found"}), 404
    if not can_access_form(get_current_user(), form_b):
        return jsonify({"message": "Forbidden"}), 403
    return jsonify(form_b.to_dict()), 200


@app.route('/api/form-b/<form_id>/reassign-reviewers', methods=['POST'])
def api_reassign_form_b_reviewers(form_id):
    user_id = session.get('id')
    user_role = (session.get('role') or '').upper()
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    if user_role not in ['ADMIN', 'SUPER_ADMIN']:
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    form = db_session.query(FormB).filter_by(form_id=form_id).first()
    if not form:
        return jsonify({'success': False, 'error': 'Form B not found'}), 404

    data = request.get_json(silent=True) or {}
    reviewer_ids = data.get('reviewer_ids') or data.get('reviewers') or []
    if not isinstance(reviewer_ids, list):
        return jsonify({'success': False, 'error': 'reviewer_ids must be a list'}), 400

    selected_ids = []
    for reviewer_id in reviewer_ids:
        reviewer_id = str(reviewer_id or '').strip()
        if reviewer_id and reviewer_id not in selected_ids:
            selected_ids.append(reviewer_id)

    if len(selected_ids) < 1 or len(selected_ids) > 2:
        return jsonify({'success': False, 'error': 'Please provide one or two reviewers'}), 400

    selected_reviewers = (
        db_session.query(User)
        .filter(
            User.user_id.in_(selected_ids),
            User.role == UserRole.REVIEWER
        )
        .all()
    )

    if len(selected_reviewers) != len(selected_ids):
        return jsonify({'success': False, 'error': 'One or more selected reviewers are invalid'}), 400

    form.reviewer_name1 = selected_ids[0]
    form.reviewer_name2 = selected_ids[1] if len(selected_ids) > 1 else None
    form.submitted_to_reviewers = True

    db_session.add(UserActivityLog(
        user_id=user_id,
        action='reassign_reviewers_api',
        page='API Form B Reassignment',
        target_user_id=form.user_id,
        details=f"Reassigned reviewers via API: {form.reviewer_name1}, {form.reviewer_name2} for FORM B {form.form_id}"
    ))
    db_session.commit()

    return jsonify({
        'success': True,
        'message': 'Form B reviewers reassigned successfully',
        'form_id': form.form_id,
        'reviewer_ids': selected_ids
    }), 200




@app.route('/form_b_upload', methods=['GET','POST'])
def form_b_upload():
    UPLOAD_FOLDER = 'static/uploads/form_b'
    user_id = session.get('id')

    if not user_id:
        return "Unauthorized", 401
    
    formA = db_session.query(FormA).filter_by(user_id=user_id).first()
    if formA:
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))
        
    formC = db_session.query(FormC).filter_by(user_id=user_id).first()
    if formC:
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))

    if request.method=='POST':
        form = db_session.query(FormB).options(
            defer(FormB.permission_letter),
            defer(FormB.prior_clearance),
            defer(FormB.ethics_evidence),
            defer(FormB.proposal_path),
            defer(FormB.pending_note),
            defer(FormB.private_permission_file)
        ).filter_by(user_id=user_id).first()
        # Get form data
        need_permission = request.form.get('need_permission')
        has_clearance = request.form.get('has_clearance')
        has_ethics_evidence = request.form.get('has_ethics_evidence')

        # Create upload folder if it doesn't exist
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)

        def get_file_blob(field_name):
            file = request.files.get(field_name)
            if file and file.filename:
                return file.read(), file.filename
            return None, None

        perm_data, perm_fname = get_file_blob('permission_letter_path')
        prior_data, prior_fname = get_file_blob('prior_clearance_path')
        pending_data, pending_fname = get_file_blob('pending_note_path')
        prop_data, prop_fname = get_file_blob('proposal_path')

        if form:
            form.user_id = user_id
            form.need_permission = need_permission == 'Yes'
            if perm_data:
                form.permission_letter = perm_data
                form.permission_letter_filename = perm_fname
            
            if pending_data:
                form.pending_note = pending_data
                form.pending_note_filename = pending_fname

            form.has_clearance = has_clearance == 'Yes'
            if prior_data:
                form.prior_clearance = prior_data
                form.prior_clearance_filename = prior_fname
            
            if prop_data:
                form.proposal_path = prop_data
                form.proposal_filename = prop_fname
        else:
            # Save to database
            form = FormB(
                user_id=user_id,
                need_permission=need_permission == 'Yes',
                permission_letter=perm_data,
                permission_letter_filename=perm_fname,
                pending_note=pending_data,
                pending_note_filename=pending_fname,
                has_clearance=has_clearance == 'Yes',
                prior_clearance=prior_data,
                prior_clearance_filename=prior_fname,
                proposal_path=prop_data,
                proposal_filename=prop_fname
            )

        db_session.add(form)
        db_session.commit()
        message="form submited succesffuly"
        return render_template("form-b-section1.html",messages=[message])

    return render_template("form-b-upload.html")


@app.route('/form_b_sec1', methods=['GET', 'POST'])
def form_b_sec1():
    try:
        if request.method == 'POST':
            user_id = session.get('id')
            if not user_id:
                return jsonify({'error': 'unauthorized'}), 401

            formA = db_session.query(FormA).filter_by(user_id=user_id).first()
            if formA:
                flash("You are not permitted to fill this form", "warning")
                return redirect(url_for("student_dashboard"))

            formC = db_session.query(FormC).filter_by(user_id=user_id).first()
            if formC:
                flash("You are not permitted to fill this form", "warning")
                return redirect(url_for("student_dashboard"))

            form_data = request.form
            user = db_session.query(User).filter(User.user_id == user_id).first()
            supervisor = db_session.query(User).filter(User.user_id == user.supervisor_id).first()

            if not user or not supervisor:
                flash("User or Supervisor not found.", "danger")
                return redirect(url_for("student_dashboard"))

            form = db_session.query(FormB).filter_by(user_id=user_id).first()

            if form:
                # Update existing record
                form.user_id = user_id
                form.applicant_name = form_data.get('applicant_name')
                form.student_number = form_data.get('student_number')
                form.institution = form_data.get('institution')
                form.department = form_data.get('department')
                form.degree = form_data.get('degree')
                form.study_title = form_data.get('study_title')
                form.mobile = form_data.get('mobile')
                form.email = user.email
                form.supervisor = supervisor.full_name
                form.supervisor_email = supervisor.email
            else:
                # Create new record
                form = FormB(
                    user_id=user_id,
                    applicant_name=form_data.get('applicant_name'),
                    student_number=form_data.get('student_number'),
                    institution=form_data.get('institution'),
                    department=form_data.get('department'),
                    degree=form_data.get('degree'),
                    study_title=form_data.get('study_title'),
                    mobile=form_data.get('mobile'),
                    email=user.email,
                    supervisor=supervisor.full_name,
                    supervisor_email=supervisor.email,
                )

            db_session.add(form)
            db_session.commit()

            message = 'Form submitted successfully'
            flash(message, 'success')
            return render_template("form-b-section2.html", messages=[message])

        # GET request
        return render_template('form-b-section1.html')

    except Exception as e:
        db_session.rollback()
        app.logger.error(f"Error in form_b_sec1: {e}")
        flash("An error occurred while submitting the form. Please try again.", "danger")
        return render_template('form-b-section1.html'), 500




@app.route('/form_b_sec2', methods=['GET', 'POST'])
def form_b_sec2():
    try:
        user_id = session.get('id')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        # Restrict access if Form A or Form C already exists
        formA = db_session.query(FormA).filter_by(user_id=user_id).first()
        if formA:
            flash("You are not permitted to fill this form", "warning")
            return redirect(url_for("student_dashboard"))
        
        formC = db_session.query(FormC).filter_by(user_id=user_id).first()
        if formC:
            flash("You are not permitted to fill this form", "warning")
            return redirect(url_for("student_dashboard"))
        
        # Handle form submission
        if request.method == 'POST':
            form_data = request.form
            form = db_session.query(FormB).filter_by(user_id=user_id).first()

            if not form:
                form = FormB(user_id=user_id)

            # ✅ Assign form fields safely
            form.project_description = form_data.get('project_description')
            form.data_nature = form_data.get('data_nature')
            form.data_origin = form_data.get('data_origin')
            form.data_public = form_data.get('data_public') == 'Yes'
            form.public_evidence = form_data.get('public_evidence')
            form.access_conditions = form_data.get('access_conditions')
            form.personal_info = form_data.get('personal_info') == 'Yes'
            form.data_anonymized = form_data.get('data_anonymized')
            form.anonymization_comment = form_data.get('anonymization_comment')
            form.private_permission = form_data.get('private_permission') == 'Yes'
            form.permission_details = form_data.get('permission_details')
            form.shortcomings_reported = form_data.get('shortcomings_reported') == 'Yes'
            form.limitations_reporting = form_data.get('limitations_reporting')
            form.methodology_alignment = form_data.get('methodology_alignment') == 'Yes'
            form.data_acknowledgment = form_data.get('data_acknowledgment')
            form.rejected_or_accepted = False

            # Handle file upload
            file = request.files.get('private_permission_file')
            if file and file.filename:
                form.private_permission_file = file.read()
                form.private_permission_filename = file.filename

            # ✅ Commit to database
            db_session.add(form)
            db_session.commit()

            message = "Section 2 saved successfully."
            flash(message, "success")
            return render_template("form-b-section3.html", messages=[message])

        # Handle GET request
        return render_template('form-b-section2.html')

    except Exception as e:
        # Roll back and log the error
        db_session.rollback()
        app.logger.error(f"Error in form_b_sec2: {e}")
        flash("An error occurred while saving your data. Please try again.", "danger")
        return render_template('form-b-section2.html'), 500

@app.route('/form_b_sec3', methods=['GET', 'POST'])
def form_b_sec3():
    try:
        user_id = session.get('id')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        if request.method == 'POST':
            form = db_session.query(FormB).filter_by(user_id=user_id).first()
            user = db_session.query(User).filter_by(user_id=user_id).first()

            if not form:
                form = FormB(user_id=user_id)

            # --- Assign form fields ---
            form.original_clearance = request.form.get('original_clearance')
            form.participant_permission = request.form.get('participant_permission')
            form.data_safekeeping = request.form.get('data_safekeeping')
            form.risk_level = request.form.get('risk_level')
            form.submitted = True
            form.risk_comments = request.form.get('risk_comments')
            form.declaration_name = request.form.get('declaration_name')
            form.full_name = request.form.get('full_name')
            form.declaration_date = datetime.now()
            form.submitted_at = datetime.now()
            form.rejected_or_accepted = False

            db_session.add(form)
            db_session.commit()

            # --- Email notification (nested try/catch) ---
            try:
                message = f"{form.applicant_name} has submitted the form and it needs to be reviewed."
                send_email(app, mail, message, [form.supervisor_email])
            except Exception as e:
                app.logger.error(f"⚠️ Failed to send email to {form.supervisor_email}: {e}")
                traceback.print_exc()

            flash("✅ Form submitted successfully.", "success")
            return redirect(url_for('student_dashboard'))

        # GET request
        return render_template('form_b_section3.html', messages=[], show_modal=False)

    except SQLAlchemyError as e:
        db_session.rollback()
        app.logger.error(f"Database error in form_b_sec3: {e}")
        traceback.print_exc()
        flash("❌ Database error occurred. Please try again.", "danger")
        return render_template('form_b_section3.html', messages=[], show_modal=False), 500

    except Exception as e:
        db_session.rollback()
        app.logger.error(f"Unexpected error in form_b_sec3: {e}")
        traceback.print_exc()
        flash("⚠️ An unexpected error occurred. Please try again.", "danger")
        return render_template('form_b_section3.html', messages=[], show_modal=False), 500





@app.route('/form_c_upload', methods=['GET'])
def form_c_upload ():
    return render_template('form-c-upload.html')

@app.route('/form_c_sec1', methods=['GET', 'POST'])
def form_c_sec1():
    try:
        if request.method == 'POST':
            user_id = session.get('id')
            if not user_id:
                return jsonify({'error': 'Unauthorized'}), 401

            # Prevent filling Form C if Form A or Form B exists
            formA = db_session.query(FormA).filter_by(user_id=user_id).first()
            if formA:
                flash("You are not permitted to fill this form", "warning")
                return redirect(url_for("student_dashboard"))

            formB = db_session.query(FormB).filter_by(user_id=user_id).first()
            if formB:
                flash("You are not permitted to fill this form", "warning")
                return redirect(url_for("student_dashboard"))

            user = db_session.query(User).filter(User.user_id == user_id).first()
            supervisor = db_session.query(User).filter(User.user_id == user.supervisor_id).first()

            if not user or not supervisor:
                flash("User or supervisor not found.", "danger")
                return redirect(url_for("student_dashboard"))

            form = db_session.query(FormC).filter_by(user_id=user_id).first()
            if not form:
                form = FormC(user_id=user_id)

            # --- Assign form fields ---
            form.applicant_name = request.form.get('applicant_name')
            form.student_number = request.form.get('student_number')
            form.institution = request.form.get('institution')
            form.department = request.form.get('department')
            form.degree = request.form.get('degree')
            form.project_title = request.form.get('project_title')
            form.mobile_number = request.form.get('mobile_number')
            form.email_address = user.email
            form.supervisor_name = supervisor.full_name
            form.supervisor_email = supervisor.email
            form.rejected_or_accepted = False
            form.supervisor_comments = ""

            db_session.add(form)
            db_session.commit()

            message = "Form submitted successfully"
            flash(message, "success")
            return render_template("form-c-section2.html", messages=[message])

        # GET request
        return render_template("form-c-section1.html")

    except Exception as e:
        db_session.rollback()
        app.logger.error(f"Error in form_c_sec1: {e}")
        flash("An error occurred while submitting the form. Please try again.", "danger")
        return render_template("form-c-section1.html"), 500


@app.route('/form_a_supervisor/<string:form_id>',methods=['GET','POST'])
@login_required
def form_a_supervisor(form_id):
    form = db_session.query(FormA).filter_by(form_id=form_id).order_by(FormA.submitted_at.desc()).first()
    if not form:
        return "Form not found", 404
    if not can_access_form(get_current_user(), form):
        abort(403)
    
    data={
        "org_name" : parse_field(form.org_name),
        "org_contact" : parse_field(form.org_contact),
        "org_role": parse_field(form.org_role),
        "org_permission" : parse_field(form.org_permission),

        "fund_org" : parse_field(form.fund_org),
        "fund_contact" :parse_field(form.fund_contact),
        "fund_role": parse_field(form.fund_role),
        "fund_amount": parse_field(form.fund_amount),

        "population" :parse_field(form.population),
        "sampling_method" : parse_field(form.sampling_method),
        "sampling_size": parse_field(form.sampling_size),
        "inclusion_criteria": parse_field(form.inclusion_criteria)
    }

    return render_template("form_a_supervisor.html",formA=form,data=data)
    
@app.route('/form_b_supervisor/<string:form_id>',methods=['GET','POST'])
@login_required
def form_b_supervisor(form_id):
    form = db_session.query(FormB).options(
        defer(FormB.permission_letter),
        defer(FormB.prior_clearance),
        defer(FormB.ethics_evidence),
        defer(FormB.proposal_path),
        defer(FormB.pending_note),
        defer(FormB.private_permission_file)
    ).filter_by(form_id=form_id).order_by(FormB.submitted_at.desc()).first()
    if not form:
        return "Form not found", 404
    if not can_access_form(get_current_user(), form):
        abort(403)

    return render_template("form_b_supervisor.html",formB=form)

@app.route('/form_c_supervisor/<string:form_id>',methods=['GET','POST'])
@login_required
def form_c_supervisor(form_id):
    ##
    ## check the user id and form id trace back the error
    ##
    form = db_session.query(FormC).filter_by(form_id=form_id).order_by(FormC.submission_date.desc()).first()
    if not form:
        return "Form not found", 404
    if not can_access_form(get_current_user(), form):
        abort(403)
    return render_template("form_c_supervisor.html",formc=form)


@app.route('/reject_or_Accept_form_a/<string:id>',methods=['GET','POST'])
def reject_or_Accept_form_a(id):

    user_id=session.get('id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        forma = db_session.query(FormA).filter_by(form_id=id).order_by(FormA.submitted_at.desc()).first()
    except ValueError as e:
        # Handle corrupted date data in database
        app.logger.error(f"Date parsing error for form {id}: {e}")
        forma = db_session.query(FormA).filter_by(form_id=id).first()
    
    #admin=db_session.query(User).filter_by(role="Admin").all()
    data={
        "org_name" : parse_field(forma.org_name) if forma else [],
        "org_contact" : parse_field(forma.org_contact) if forma else [],
        "org_role": parse_field(forma.org_role) if forma else [],
        "org_permission" : parse_field(forma.org_permission) if forma else [],

        "fund_org" : parse_field(forma.fund_org) if forma else [],
        "fund_contact" :parse_field(forma.fund_contact) if forma else [],
        "fund_role": parse_field(forma.fund_role) if forma else [],
        "fund_amount": parse_field(forma.fund_amount) if forma else [],

        "population" :parse_field(forma.population) if forma else [],
        "sampling_method" : parse_field(forma.sampling_method) if forma else [],
        "sampling_size": parse_field(forma.sampling_size) if forma else [],
        "inclusion_criteria": parse_field(forma.inclusion_criteria) if forma else []
    }

    if not forma:
        forma = FormA(form_id=id)
    if request.method=="POST":
        org_permission_comment=(request.form.get('org_permission_comment') or '').strip()
        waiver_comment=(request.form.get('waiver_comment') or '').strip()
        form_a_comment=(request.form.get('form_a_comment') or '').strip()
        questions_comment=(request.form.get('questions_comment') or '').strip()
        consent_comment=(request.form.get('consent_comment') or '').strip()
        proposal_comment=(request.form.get('proposal_comment') or '').strip()
        supervisor_feedback=(request.form.get('supervisor_feedback') or '').strip()
        recommendation=request.form.get('recommendation')
        supervisor_signature=(request.form.get('supervisor_signature') or '').strip()
        signature_date=datetime.now()

        if not supervisor_feedback:
            flash('Supervisor feedback is required before submitting your recommendation.', 'danger')
            return redirect(url_for('form_a_supervisor', form_id=id))
        
        
        if request.form.get('recommendation')=='Ready for submission':
            if not supervisor_signature:
                flash('Supervisor signature is required when approving for submission.', 'danger')
                return redirect(url_for('form_a_supervisor', form_id=id))
            forma.supervisor_date=datetime.now()
            forma.org_permission_comment=org_permission_comment
            forma.waiver_comment=waiver_comment
            forma.form_a_comment=form_a_comment
            forma.questions_comment=questions_comment
            forma.consent_comment=consent_comment
            forma.proposal_comment=proposal_comment
            forma.supervisor_feedback=supervisor_feedback
            forma.recommendation=recommendation
            forma.supervisor_signature=supervisor_signature
            forma.signature_date=signature_date
            forma.rejected_or_accepted=True
            forma.submitted_to_admin=True
            #Uncomment the code bellow for testing
            ##
            try:
                message=f' Form belongning to {forma.applicant_name} has been reviewed by the supervisor and has been accepted for further reviewing. ' 
            
                send_email(app,mail, message,[forma.email])
            except Exception as e:
                app.logger.error(f"Failed to send email to {forma.email}: {e}")
        else:
            reject=request.form.get('reject')
            forma.supervisor_date=datetime.now()
            forma.org_permission_comment=org_permission_comment
            forma.waiver_comment=waiver_comment
            forma.form_a_comment=form_a_comment
            forma.questions_comment=questions_comment
            forma.consent_comment=consent_comment
            forma.proposal_comment=proposal_comment
            forma.supervisor_feedback=supervisor_feedback
            forma.recommendation=recommendation
            forma.form_supervisor_status=reject
            forma.supervisor_signature=None
            forma.signature_date=None
            forma.rejected_or_accepted=False
            try:
                message=f' Form belonging to {forma.applicant_name} has been reviewed and returned back to you. Please login to view the feedback.' 
            
                send_email(app,mail, message,[forma.email])
                
            except Exception as e:
                app.logger.error(f"Failed to send email to {forma.email}: {e}")

                

                # New form flow: respect dashboard origin when present
                from_dashboard = request.form.get('from_dashboard') or request.args.get('from_dashboard')
                if from_dashboard:
                    return redirect(url_for('dashboard'))
        db_session.add(forma)
        db_session.commit()
    return redirect(url_for('supervisor_dashboard'))

@app.route('/reject_or_Accept_form_b/<string:id>',methods=['GET','POST'])
def reject_or_Accept_form_b(id):
    user_id=session.get('id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        formb = db_session.query(FormB).options(
            defer(FormB.permission_letter),
            defer(FormB.prior_clearance),
            defer(FormB.ethics_evidence),
            defer(FormB.proposal_path),
            defer(FormB.pending_note),
            defer(FormB.private_permission_file)
        ).filter_by(form_id=id).order_by(FormB.submitted_at.desc()).first()
    except ValueError as e:
        # Handle corrupted date data in database
        app.logger.error(f"Date parsing error for form {id}: {e}")
        formb = db_session.query(FormB).options(
            defer(FormB.permission_letter),
            defer(FormB.prior_clearance),
            defer(FormB.ethics_evidence),
            defer(FormB.proposal_path),
            defer(FormB.pending_note),
            defer(FormB.private_permission_file)
        ).filter_by(form_id=id).first()
    #admin=db_session.query(User).filter_by(role="Admin").all()
    if not formb:
        formb = FormB(form_id=id)
    if request.method=="POST":
 
        org_permission_comment=(request.form.get('org_permission_comment') or '').strip()
        waiver_comment=(request.form.get('waiver_comment') or '').strip()
        form_a_comment=(request.form.get('form_a_comment') or '').strip()
        questions_comment=(request.form.get('questions_comment') or '').strip()
        consent_comment=(request.form.get('consent_comment') or '').strip()
        proposal_comment=(request.form.get('proposal_comment') or '').strip()
        supervisor_feedback=(request.form.get('supervisor_feedback') or '').strip()
        recommendation=request.form.get('recommendation')
        supervisor_signature=(request.form.get('supervisor_signature') or '').strip()
        signature_date=datetime.now()
        reject=request.form.get('reject')

        if not supervisor_feedback:
            flash('Supervisor feedback is required before submitting your recommendation.', 'danger')
            return redirect(url_for('form_b_supervisor', form_id=id))

        if request.form.get('recommendation')=='Ready for submission':
            if not supervisor_signature:
                flash('Supervisor signature is required when approving for submission.', 'danger')
                return redirect(url_for('form_b_supervisor', form_id=id))
            formb.supervisor_date=datetime.now()
            formb.org_permission_comment=org_permission_comment
            formb.waiver_comment=waiver_comment
            formb.form_a_comment=form_a_comment
            formb.questions_comment=questions_comment
            formb.consent_comment=consent_comment
            formb.proposal_comment=proposal_comment
            formb.supervisor_feedback=supervisor_feedback
            formb.recommendation=recommendation
            formb.supervisor_signature=supervisor_signature
            formb.signature_date=signature_date
            formb.rejected_or_accepted=True
            formb.submitted_to_admin=True
            #Uncomment the code bellow for testing
            ##
            try:
                message=f' Form belongning to {formb.applicant_name} has been reviewed by the supervisor and has been accepted for further reviewing.' 
            
                send_email(app,mail, message,[formb.email])
            except Exception as e:
                app.logger.error(f"Failed to send email to {formb.email}: {e}")
            
        else:
            formb.supervisor_date=datetime.now()
            formb.org_permission_comment=org_permission_comment
            formb.waiver_comment=waiver_comment
            formb.form_a_comment=form_a_comment
            formb.questions_comment=questions_comment
            formb.consent_comment=consent_comment
            formb.proposal_comment=proposal_comment
            formb.supervisor_feedback=supervisor_feedback
            formb.recommendation=recommendation
            formb.form_supervisor_status=reject
            formb.supervisor_signature=None
            formb.signature_date=None
            formb.rejected_or_accepted=False
            try:
                message=f'Form belonging to {formb.applicant_name} has been reviewed and returned back to you. Please login to view the feedback.' 
            
                send_email(app,mail, message,[formb.email])
            except Exception as e:
                app.logger.error(f"Failed to send email to {formb.email}: {e}")
            

        
        db_session.add(formb)
        db_session.commit()
    return redirect(url_for('supervisor_dashboard'))


@app.route('/reject_or_Accept_form_c/<string:id>',methods=['GET','POST'])
def reject_or_Accept_form_c(id):
    user_id=session.get('id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        formc = db_session.query(FormC).filter_by(form_id=id).order_by(FormC.submission_date.desc()).first()
    except ValueError as e:
        # Handle corrupted date data in database
        app.logger.error(f"Date parsing error for form {id}: {e}")
        formc = db_session.query(FormC).filter_by(form_id=id).first()
    #admin=db_session.query(User).filter_by(role="Admin").all()
    if not formc:
        formc = FormC(form_id=id)
    if request.method=="POST":
        org_permission_comment=(request.form.get('org_permission_comment') or '').strip()
        waiver_comment=(request.form.get('waiver_comment') or '').strip()
        form_a_comment=(request.form.get('form_a_comment') or '').strip()
        questions_comment=(request.form.get('questions_comment') or '').strip()
        consent_comment=(request.form.get('consent_comment') or '').strip()
        proposal_comment=(request.form.get('proposal_comment') or '').strip()
        supervisor_feedback=(request.form.get('supervisor_feedback') or '').strip()
        recommendation=request.form.get('recommendation')
        supervisor_signature=(request.form.get('supervisor_signature') or '').strip()
        reject=request.form.get('reject')
        signature_date=datetime.now()

        if not supervisor_feedback:
            flash('Supervisor feedback is required before submitting your recommendation.', 'danger')
            return redirect(url_for('form_c_supervisor', form_id=id))
        
        if request.form.get('recommendation')=='Ready for submission':
            if not supervisor_signature:
                flash('Supervisor signature is required when approving for submission.', 'danger')
                return redirect(url_for('form_c_supervisor', form_id=id))
            formc.supervisor_date=datetime.now()
            formc.org_permission_comment=org_permission_comment
            formc.waiver_comment=waiver_comment
            formc.form_a_comment=form_a_comment
            formc.questions_comment=questions_comment
            formc.consent_comment=consent_comment
            formc.proposal_comment=proposal_comment
            formc.supervisor_feedback=supervisor_feedback
            formc.recommendation=recommendation
            formc.supervisor_signature=supervisor_signature
            formc.signature_date=signature_date
            formc.rejected_or_accepted=True
            formc.submitted_to_admin=True
            #Uncomment the code bellow for testing
            ##
            try:
                message=f'Form belongning to {formc.applicant_name} has been reviewed by the supervisor and has been accepted for further reviewing.' 
            
                send_email(app,mail, message,[formc.email_address])
            except Exception as e:
                app.logger.error(f"Failed to send email to {formc.email_address}: {e}")
             
        else:
            formc.supervisor_date=datetime.now()
            formc.org_permission_comment=org_permission_comment
            formc.waiver_comment=waiver_comment
            formc.form_a_comment=form_a_comment
            formc.questions_comment=questions_comment
            formc.consent_comment=consent_comment
            formc.proposal_comment=proposal_comment
            formc.supervisor_feedback=supervisor_feedback
            formc.form_supervisor_status=reject
            formc.recommendation=recommendation
            formc.supervisor_signature=None
            formc.signature_date=None
            formc.rejected_or_accepted=False
            try:
                message=f' Form belonging to {formc.applicant_name} has been reviewed and returned back to you. Please login to view the feedback.' 
            
                send_email(app,mail, message,[formc.email_address])
            except Exception as e:
                app.logger.error(f"Failed to send email to {formc.email_address}: {e}")
                
        db_session.add(formc)
        db_session.commit()
    return redirect(url_for('supervisor_dashboard'))

@app.route('/form_c_sec2', methods=['GET', 'POST'])
def form_c_sec2():
    try:
        user_id = session.get('id')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        if request.method == "POST":
            form = db_session.query(FormC).filter_by(user_id=user_id).first()
            if not form:
                form = FormC(user_id=user_id)

            # --- Map boolean fields ---
            boolean_fields = {
                'vulnerable': 'vulnerable',
                'age_under_18_or_over_65': 'age_under_18_or_over_65',
                'uj_employee': 'uj_employees',
                'non_vulnerable_context': 'non_vulnerable_context',
                'non_english': 'non_english',
                'own_student': 'own_students',
                'poverty': 'poverty',
                'non_education': 'no_education',
                'consent_violation': 'consent_violation',
                'discomfiture': 'discomfiture',
                'deception': 'deception',
                'sensitive_issues': 'sensitive_issues',
                'prejuditial_info': 'prejudicial_info',
                'intrusive': 'intrusive',
                'illegal': 'illegal',
                'direct_social_info': 'direct_social_info',
                'identifiable_records': 'identifiable_records',
                'psychology_tests': 'psychology_tests',
                'reseacher_risk': 'researcher_risk',
                'incentives': 'incentives',
                'participant_costs': 'participant_costs',
                'researcher_interest': 'researcher_interest',
                'conflict_of_interest': 'conflict_of_interest',
                'uj_premises': 'uj_premises',
                'uj_facilities': 'uj_facilities',
                'uj_funding': 'uj_funding'
            }

            for form_field, model_field in boolean_fields.items():
                setattr(form, model_field, request.form.get(form_field) == "Yes")

            # --- Map text fields ---
            text_fields = [
                'vulnerable_other_description',
                'vulnerable_comments',
                'activity_other_description',
                'activity_comments',
                'consideration_comments',
                'risk_level',
                'risk_justification',
                'risk_benefits',
                'risk_mitigation'
            ]

            for field in text_fields:
                setattr(form, field, request.form.get(field))

            db_session.add(form)
            db_session.commit()

            message = "Form submitted successfully"
            flash(message, "success")
            return render_template("form-c-section3.html", messages=[message])

        # GET request
        return render_template("form-c-section2.html")

    except Exception as e:
        db_session.rollback()
        app.logger.error(f"Error in form_c_sec2: {e}")
        flash("An error occurred while submitting the form. Please try again.", "danger")
        return render_template("form-c-section2.html"), 500


@app.route('/form_c_sec3', methods=['GET', 'POST'])
def form_c_sec3():
    try:
        user_id = session.get('id')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        if request.method == "POST":
            form = db_session.query(FormC).filter_by(user_id=user_id).first()
            if not form:
                form = FormC(user_id=user_id)

            # --- Map text fields dynamically ---
            text_fields = [
                'summary_title',
                'executive_summary',
                'research_questions',
                'research_purpose',
                'secondary_data_info',
                'exemption_reason'
            ]

            for field in text_fields:
                setattr(form, field, request.form.get(field))

            db_session.add(form)
            db_session.commit()

            message = "Form submitted successfully"
            flash(message, "success")
            return render_template("form-c-section4.html", messages=[message])

        # GET request
        return render_template("form-c-section3.html")

    except Exception as e:
        db_session.rollback()
        app.logger.error(f"Error in form_c_sec3: {e}")
        flash("An error occurred while submitting the form. Please try again.", "danger")
        return render_template("form-c-section3.html"), 500


@app.route('/form_c_sec4', methods=['GET', 'POST'])
def form_c_sec4():
    try:
        user_id = session.get('id')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        if request.method == "POST":
            form = db_session.query(FormC).filter_by(user_id=user_id).first()
            user = db_session.query(User).filter_by(user_id=user_id).first()

            if not form:
                form = FormC(user_id=user_id)

            # Update form declaration fields
            form.declaration_name = request.form.get('declaration_name')
            form.full_name = request.form.get('full_name')
            form.submitted = True
            form.submission_date = datetime.now()

            db_session.add(form)
            db_session.commit()

            # Try sending notification email
            try:
                message = f'{form.applicant_name} has submitted a form that needs to be reviewed.'
                send_email(app, mail, message, [form.supervisor_email])
            except Exception as e:
                app.logger.error(f"Failed to send email to {form.supervisor_email}: {e}")

            flash("Form submitted successfully", "success")
            return redirect(url_for('student_dashboard'))

        # GET request
        return render_template("form-c-section4.html")

    except Exception as e:
        db_session.rollback()
        app.logger.error(f"Error in form_c_sec4: {e}")
        flash("An error occurred while submitting the form. Please try again.", "danger")
        return render_template("form-c-section4.html"), 500


@app.route('/form_a_answers', methods=['GET','POST'])
def form_a_answers():
    user_id=session.get('id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    form = db_session.query(FormA).filter_by(user_id=user_id).first()

    return render_template("form_a_answers.html",formA=form)


@app.route('/student_edit_forma', methods=['GET','POST'])
def student_edit_forma():
    user_id=session.get('id')



    formB = db_session.query(FormB).options(
        defer(FormB.permission_letter),
        defer(FormB.prior_clearance),
        defer(FormB.ethics_evidence),
        defer(FormB.proposal_path),
        defer(FormB.pending_note),
        defer(FormB.private_permission_file)
    ).filter_by(user_id=user_id).order_by(FormB.submitted_at.asc()).first()
    if formB:
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))
        
    formC = db_session.query(FormC).filter_by(user_id=user_id).first()
    if formC:
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))
    

    public_data_description=""
    private_permission_file=None
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    user = db_session.query(User).filter(User.user_id == user_id).first()
    supervisor=db_session.query(User).filter(User.user_id == user.supervisor_id).first()
    
    form = (
        db_session.query(FormA)
        .filter_by(user_id=user_id)
        .order_by(FormA.submitted_at.desc().nullslast(), FormA.created_at.desc().nullslast())
        .first()
    )

    form_requirements = db_session.query(FormARequirements).filter(FormARequirements.user_id == user_id).first()

    source_form = form

    if form:
        data_org={
            "org_name" : parse_field(form.org_name),
            "org_contact" : parse_field(form.org_contact),
            "org_role": parse_field(form.org_role),
            "org_permission" : parse_field(form.org_permission),
            }
        data_fund={
                "fund_org" : parse_field(form.fund_org),
                "fund_contact" :parse_field(form.fund_contact),
                "fund_role": parse_field(form.fund_role),
                "fund_amount": parse_field(form.fund_amount),
            }
        data_sampling={
                "population" :parse_field(form.population),
                "sampling_method" : parse_field(form.sampling_method),
                "sampling_size": parse_field(form.sampling_size),
                "inclusion_criteria": parse_field(form.inclusion_criteria)
            }
        data_store={
            'data':parse_field(form.data_storage)
        }

        _privacy={
            'privacy':parse_field(form.privacy)
        }
    else:
        data_org={"org_name": [], "org_contact": [], "org_role": [], "org_permission": []}
        data_fund={"fund_org": [], "fund_contact": [], "fund_role": [], "fund_amount": []}
        data_sampling={"population": [], "sampling_method": [], "sampling_size": [], "inclusion_criteria": []}
        data_store={'data': []}
        _privacy={'privacy': []}
        form = FormA(user_id=user_id)
        inherit_previous_reviewers(form, FormA, user_id, FormA.submitted_at)
    if request.method == 'POST':
        was_in_corrections = is_student_correction_state(source_form)
        cleaned_sample_sizes, sample_size_error = _normalize_sampling_size_list(request.form.getlist('sample_size[]'))
        if sample_size_error:
            flash(sample_size_error, "danger")
            return redirect(url_for('student_edit_forma'))
      
        if request.form.get('survey')=='Yes':
            survey=True
        else:
            survey=False

        if request.form.get('focus_groups')=='Yes':
            focus_groups=True
        else:
            focus_groups=False

        if request.form.get('observations')=='Yes':
            observations=True
        else:
            observations=False

        if request.form.get('interviews')=='Yes':
            interviews=True
        else:
            interviews=False

        if request.form.get('documents')=='Yes':
            documents=True
        else:
            documents=False
        
        if request.form.get('vulnerable_other_specify')=='Yes':
            vulnerable_other_specify=True
        else:
            vulnerable_other_specify=False

        # section 2.1
        if request.form.get('vulnerable_communities')=='Yes':
            vulnerable_communities=True
        else:
            vulnerable_communities=False

        if request.form.get('age_range')=='Yes':
            age_range=True
        else:
            age_range=False

        if request.form.get('uj_employees')=='Yes':
            uj_employees=True
        else:
            uj_employees=False

        if request.form.get('vulnerable')=='Yes':
            vulnerable=True
        else:
            vulnerable=False

        if request.form.get('non_english')=='Yes':
            non_english=True
        else:
            non_english=False

        if request.form.get('own_students')=='Yes':
            own_students=True
        else:
            own_students=False

        if request.form.get('poverty')=='Yes':
            poverty=True
        else:
            poverty=False
        
        if request.form.get('no_education')=='Yes':
            no_education=True
        else:
            no_education=False
        
        if form:
            form.assessment_other_specify = request.form.get('assessment_other_specify')

        if request.form.get('vulnerable_comments_1')=='Yes':
            vulnerable_comments_1=True
        else:
            vulnerable_comments_1=False

        # 2.2
        if request.form.get('disclosure')=='Yes':
            disclosure=True
        else:
            disclosure=False

        if request.form.get('discomfiture')=='Yes':
            discomfiture=True
        else:
            discomfiture=False

        if request.form.get('deception')=='Yes':
            deception=True
        else:
            deception=False
        
        if request.form.get('sensitive')=='Yes':
            sensitive=True
        else:
            sensitive=False

        if request.form.get('prejudice')=='Yes':
            prejudice=True
        else:
            prejudice=False

        
        if request.form.get('intrusive_techniques')=='Yes':
            intrusive_techniques=True
        else:
            intrusive_techniques=False

        if request.form.get('illegal_activities')=='Yes':
            illegal_activities=True
        else:
            illegal_activities=False

        if request.form.get('personal')=='Yes':
            personal=True
        else:
            personal=False
            
        if request.form.get('available_records')=='Yes':
            available_records=True
        else:
            available_records=False

        if request.form.get('inventories')=='Yes':
            inventories=True
        else:
            inventories=False

        if request.form.get('risk_activities')=='Yes':
            risk_activities=True
        else:
            risk_activities=False

        if request.form.get('activity_specify')=='Yes':
            activity_specify=True
        else:
            activity_specify=False
        
        if request.form.get('vulnerable_comments_2')=='Yes':
            vulnerable_comments_2=True
        else:
            vulnerable_comments_2=False
        
        # Risk Assessment 2.3
        if request.form.get('incentives')=='Yes':
            incentives=True
        else:
            incentives=False

        if request.form.get('financial_costs')=='Yes':
            financial_costs=True
        else:
            financial_costs=False

        if request.form.get('reward')=='Yes':
            reward=True
        else:
            reward=False
        
        if request.form.get('conflict')=='Yes':
            conflict=True
        else:
            conflict=False

        if request.form.get('uj_premises')=='Yes':
            uj_premises=True
        else:
            uj_premises=False
  
        if request.form.get('uj_facilities')=='Yes':
            uj_facilities=True
        else:
            uj_facilities=False

        if request.form.get('uj_funding')=='Yes':
            uj_funding=True
        else:
            uj_funding=False
        
        form.vulnerable_comments_3=request.form.get('vulnerable_comments_3')
        
        if request.form.get('dataType') == 'public':
                public_data_description = request.form.get('public_data_description')

        if request.form.get('researcher_affiliation')=='Yes':
            researcher_affiliation=True
        else:
            researcher_affiliation=False

        if request.form.get('collective_involvement')=='Yes':
            collective_involvement=True
        else:
            collective_involvement=False
       
        secondary_data = request.form.get('secondary_data')  # This should be added as a hidden input for access
        
        if secondary_data == 'No':
            if form:
                form.uses_secondary_data = False
        else:
            if form:
                form.uses_secondary_data = True
                form.secondary_data_type = request.form.get('data_type')
                if form.secondary_data_type == 'private':
                    form.private_permission = request.form.get('privatePermission') == 'Yes'
                    # Handle file upload for permission if required
                    # Add logic for saving file securely if uploaded
                elif form.secondary_data_type == 'public':
                    form.public_data_description = request.form.get('public_data_description')
            
        
            
        if request.form.get('translator')=='Yes':
            translator=True
        else:
            translator=False

        if request.form.get('intervention')=='Yes':
            intervention=True
        else:
            intervention=False


        if request.form.get('use_focus_groups')=='Yes':
            use_focus_groups=True

        else:
            use_focus_groups=False


        if request.form.get('conflict_interest')=='Yes':
            conflict_interest=True
        else:
            conflict_interest=False

        
        data_nature=request.form.get('data_nature')
        data_origin=request.form.get('data_origin')
        access_conditions=request.form.get('access_conditions')
        personal_info=request.form.get('personal_info')
        personal_info_comment=request.form.get('personal_info_comment')
        data_anonymized=request.form.get('data_anonymized')
        anonymization_comment=request.form.get('anonymization_comment')
      
        permission_details=request.form.get('permission_details')
        public_data_description=request.form.get('public_data_description')
        shortcomings_reported=request.form.get('shortcomings_reported')
        limitations_reporting=request.form.get('limitations_reporting')
        methodology_alignment=request.form.get('methodology_alignment')
        data_acknowledgment=request.form.get('data_acknowledgment')
        if form:
            form.observation_details = request.form.get('observation_details')
            form.documents_details = request.form.get('documents_details')

        interviews_one = request.form.get('interviews') == 'Yes'
        documents_one = request.form.get('documents') == 'Yes'
        
        form = FormA(user_id=user_id)
        inherit_previous_reviewers(form, FormA, user_id, FormA.submitted_at)
        db_session.add(form)

        # Handle file upload
        file = request.files.get('private_permission_file')
        if file and file.filename:
            form.private_permission_file = file.read()
            form.private_permission_filename = file.filename

        # Update the form attributes
        form.attachment_id = form_requirements.id
        form.applicant_name = request.form.get('applicant_name')
        form.student_number = request.form.get('student_number')
        form.institution = request.form.get('institution')
        form.department = request.form.get('department')
        form.degree = request.form.get('degree')
        form.study_title = request.form.get('study_title')
        form.mobile = request.form.get('mobile')
        form.email = user.email
        form.supervisor = supervisor.full_name
        form.supervisor_email = supervisor.email
        form.survey = survey
        form.observations = observations
        form.focus_groups = focus_groups
        form.interviews = interviews
        form.documents = documents
        form.vulnerable_other_specify = vulnerable_other_specify
        form.vulnerable_communities = vulnerable_communities
        form.age_range = age_range
        form.uj_employees = uj_employees
        form.vulnerable = vulnerable
        form.non_english = non_english
        form.own_students = own_students
        form.poverty = poverty
        form.no_education = no_education
        form.assessment_other_specify = request.form.get('assessment_other_specify')
        form.vulnerable_comments_1 = vulnerable_comments_1
        form.disclosure = disclosure
        form.discomfiture = discomfiture
        form.deception = deception
        form.sensitive = sensitive
        form.prejudice = prejudice
        form.intrusive_techniques = intrusive_techniques
        form.illegal_activities = illegal_activities
        form.personal = personal
        form.available_records = available_records
        form.inventories = inventories
        form.risk_activities = risk_activities
        form.activity_specify = activity_specify
        form.vulnerable_comments_2 = vulnerable_comments_2
        form.incentives = incentives
        form.financial_costs = financial_costs
        form.reward = reward
        form.conflict = conflict
        form.uj_premises = uj_premises
        form.uj_facilities = uj_facilities
        form.uj_funding = uj_funding
        form.vulnerable_comments_3 = request.form.get('vulnerable_comments_3')
        form.risk_rating = request.form.get('risk_rating')
        form.risk_justification = request.form.get('risk_justification')
        form.benefits_description = request.form.get('benefits_description')
        form.risk_mitigation = request.form.get('risk_mitigation')

        form.interviews_one = interviews_one
        form.documents_one = documents_one
        form.other_sec2 = request.form.get('other_sec2')
        
        # Section 3: Project Information
        form.title_provision = request.form.get('title_provision')
        form.abstract = request.form.get('abstract')
        form.questions = request.form.get('questions')
        form.purpose_objectives = request.form.get('purpose_objectives')

        # Section 4: Organisational Permissions and Affiliations
        form.grant_permission = request.form.get('grant_permission')
        form.org_name = ','.join(request.form.getlist('org_name[]'))
        form.org_contact = ','.join(request.form.getlist('org_contact[]'))
        form.org_role = ','.join(request.form.getlist('org_role[]'))
        form.org_permission = ','.join(request.form.getlist('org_permission[]'))
        
        form.researcher_affiliation = 'Yes' if researcher_affiliation else 'No'
        form.affiliation_details = request.form.get('affiliation_details')

        form.collective_involvement = 'Yes' if collective_involvement else 'No'
        form.collective_details = request.form.get('collective_details')
        
        # Funding Information
        form.is_funded = request.form.get('is_funded')
        form.fund_org = ','.join(request.form.getlist('fund_org[]'))
        form.fund_contact = ','.join(request.form.getlist('fund_contact[]'))
        form.fund_role = ','.join(request.form.getlist('fund_role[]'))
        form.fund_amount = ','.join(request.form.getlist('fund_amount[]'))
        
        # Indemnity & Other Committee Info
        form.indemnity_arrangements = request.form.get('indemnity_arrangements')
        form.other_committee = request.form.get('other_committee')
        
        # 5.1 Research Paradigm
        form.quantitative = "Yes" in request.form.getlist('quantitative[]')
        form.qualitative = "Yes" in request.form.getlist('qualitative[]')
        form.mixed_methods = "Yes" in request.form.getlist('mixed_methods[]')
        form.paradigm_explanation = request.form.get('paradigm_explanation')

        # 5.2 Research Design
        form.design = request.form.get('design')

        # 5.3 Participant Details
        form.participants_description = request.form.get('participants_description')
        form.population = ','.join(request.form.getlist('population[]'))
        form.sampling_method = ','.join(request.form.getlist('sampling_method[]'))
        form.sampling_size = ','.join(cleaned_sample_sizes)
        form.inclusion_criteria = ','.join(request.form.getlist('inclusion_criteria[]'))
        form.duration_timing = request.form.get('duration_timing')
        form.contact_details_method = request.form.get('contact_details_method')
        form.conflict_interest = conflict_interest
        form.conflict_explanation = request.form.get('conflict_explanation')

        # 5.4 Instruments
        form.questionnaire_type = request.form.get('questionnaire_type')
        questionnaire_permission = request.form.get('questionnaire_permission')
        if questionnaire_permission is not None:
            questionnaire_permission = questionnaire_permission.strip()
            if questionnaire_permission == 'Yes':
                form.permission_obtained = 'Yes'
                form.open_source = 'No'
            elif questionnaire_permission == 'Open Source':
                form.permission_obtained = 'No'
                form.open_source = 'Yes'
            else:
                form.permission_obtained = None
                form.open_source = None
        else:
            form.permission_obtained = request.form.get('permission_obtained')
            form.open_source = request.form.get('open_source')
        form.instrument_attachment_reason = request.form.get('instrument_attachment_reason')
        form.data_collection_procedure = request.form.get('data_collection_procedure')
        form.interview_type = request.form.get('interview_type')
        form.interview_recording = request.form.get('interview_recording')
        form.focus_recording = request.form.get('focus_recording')
        form.data_collectors = request.form.get('data_collectors')
        form.data_methods = ','.join(request.form.getlist('data_methods[]'))
        form.intervention = intervention
        form.intervention_details = request.form.get('intervention_details')
        form.sensitive_data = request.form.get('sensitive_data')
        form.translator = translator
        form.translator_procedure = request.form.get('translator_procedure')

        # 5.5 Secondary Data Usage
        form.data_nature = data_nature
        form.data_origin = data_origin
        form.access_conditions = access_conditions
        form.personal_info = personal_info
        form.personal_info_comment = personal_info_comment
        form.data_anonymized = data_anonymized
        form.anonymization_comment = anonymization_comment
        form.permission_details = permission_details
        form.shortcomings_reported = shortcomings_reported
        form.limitations_reporting = limitations_reporting
        form.methodology_alignment = methodology_alignment
        form.data_acknowledgment = data_acknowledgment
        form.private_permission = request.form.get('privatePermission')
        form.public_data_description = public_data_description
        form.informed_consent = request.form.get('informed_consent')
        form.secure_location = ','.join(request.form.getlist('secure_location[]'))
        form.password_protected = ','.join(request.form.getlist('password_protected[]'))
        form.protected_place = ','.join(request.form.getlist('protected_place[]'))
        form.retention = ','.join(request.form.getlist('retention[]'))
        form.data_storage = ','.join(request.form.getlist('data_storage[]'))
        form.study_benefits = request.form.get('study_benefits')
        form.participant_risks = request.form.get('participant_risks')
        form.adverse_steps = request.form.get('adverse_steps')
        form.community_participation = request.form.get('community_participation')
        form.community_effects = request.form.get('community_effects')
        
        form.privacy = ','.join(request.form.getlist('privacy[]'))
        form.q6_9a = request.form.get("q6_9a") == 'yes'
        form.q6_9b = request.form.get("q6_9b") == 'yes'
        form.q6_9c = request.form.get("q6_9c") == 'yes'
        form.q6_9d = request.form.get("q6_9d") == 'yes'
        form.q6_9e = request.form.get("q6_9e") == 'yes'
        form.q6_9f = request.form.get("q6_9f") == 'yes'
        form.q6_9g = request.form.get("q6_9g") == 'yes'
        form.q6_9h = request.form.get("q6_9h") == 'yes'
        form.q6_9i = request.form.get("q6_9i") == 'yes'
        form.q6_9j = request.form.get("q6_9j") == 'yes'
        form.q6_9k = request.form.get("q6_9k") == 'yes'
        form.q6_9l = request.form.get("q6_9l") == 'yes'
        form.q6_9m = request.form.get("q6_9m") == 'yes'
        form.q6_9n = request.form.get("q6_9n") == 'yes'
        form.q6_9o = request.form.get("q6_9o") == 'yes'
        form.q6_9p = request.form.get("q6_9p") == 'yes'
        form.q6_9q = request.form.get("q6_9q") == 'yes'
        form.q6_9r = request.form.get("q6_9r") == 'yes'
        form.q6_9s = request.form.get("q6_9s") == 'yes'
        form.results_feedback = request.form.get('results_feedback')
        form.products_access = request.form.get('products_access')
        form.publication_plans = request.form.get('publication_plans')
        form.participant_comp = request.form.get('participant_comp')
        form.participant_costs = request.form.get('participant_costs')
        form.ethics_reporting = request.form.get('ethics_reporting')
        
        # Declaration fields - must be explicitly filled by student
        declaration_name = request.form.get('declaration_name', '').strip()
        applicant_signature = request.form.get('applicant_signature', '').strip()
        
        if declaration_name and applicant_signature:
            form.declaration_name = declaration_name
            form.applicant_signature = applicant_signature
            form.declaration_date = datetime.now()
            form.submitted = True
            form.submitted_at = datetime.now()
            form.rejected_or_accepted = False
            form.status = 'Resubmitted' if was_in_corrections else 'Submitted'
            form.visible_to_student = False
            form.ethics_form_status = 'Resubmitted' if was_in_corrections else 'Submitted'
            form.form_supervisor_status = 'Resubmitted' if was_in_corrections else 'Submitted'
            reset_form_review_feedback(form)
        else:
            # If declaration not filled, form is not submitted
            flash('Declaration section must be completed to submit the form', 'warning')
            return redirect(url_for('student_edit_forma'))
        
        db_session.commit()
        
        #Uncomment the code bellow for testing
        ##
        try:
            message=(f'you have successfully edited and submitted your form. ' 
            f'Please wait while its under review.')
            
            send_email(app,mail, message,[user.email])

            messages=(f'{ form.applicant_name} has submitted a form that needs to be reviewed. ')
            
            send_email(app,mail, messages,[form.supervisor_email])
        except Exception as e:
                print("Email sending error:", str(e))

        return redirect(url_for('student_dashboard'))
    return render_template("student_edit_forma.html",formA=form,data_org=data_org,data_fund=data_fund,data_sampling=data_sampling,data_storage=data_store,privacy=_privacy)


@app.route('/student_continue_forma', methods=['GET','POST'])
def student_continue_forma():
    user_id=session.get('id')

    formB = db_session.query(FormB).filter_by(user_id=user_id).order_by(FormB.submitted_at.asc()).first()
    if formB:
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))
        
    formC = db_session.query(FormC).filter_by(user_id=user_id).first()
    if formC:
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))
    

    public_data_description=""
    private_permission_file=None
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    user = db_session.query(User).filter(User.user_id == user_id).first()
    supervisor=db_session.query(User).filter(User.user_id == user.supervisor_id).first()
    
    # Check if form exists in database - if yes UPDATE, if no CREATE
    form = _get_latest_forma_for_user(user_id)
        
        
    
   
    form_requirements = db_session.query(FormARequirements).filter(FormARequirements.user_id == user_id).first()
    data_org={
            "org_name" : parse_field(form.org_name),
            "org_contact" : parse_field(form.org_contact),
            "org_role": parse_field(form.org_role),
            "org_permission" : parse_field(form.org_permission),
        }
    data_fund={
            "fund_org" : parse_field(form.fund_org),
            "fund_contact" :parse_field(form.fund_contact),
            "fund_role": parse_field(form.fund_role),
            "fund_amount": parse_field(form.fund_amount),
        }
    data_sampling={
            "population" :parse_field(form.population),
            "sampling_method" : parse_field(form.sampling_method),
            "sampling_size": parse_field(form.sampling_size),
            "inclusion_criteria": parse_field(form.inclusion_criteria)
        }
        
    if request.method == 'POST':
        try:
            cleaned_sample_sizes, sample_size_error = _normalize_sampling_size_list(request.form.getlist('sample_size[]'))
            if sample_size_error:
                flash(sample_size_error, "danger")
                return redirect(url_for('student_continue_forma'))

            if request.form.get('survey')=='Yes':
                survey=True
            else:
                survey=False

            if request.form.get('focus_groups')=='Yes':
                focus_groups=True
            else:
                focus_groups=False

            if request.form.get('observations')=='Yes':
                observations=True
            else:
                observations=False

            if request.form.get('interviews')=='Yes':
                interviews=True
            else:
                interviews=False

            if request.form.get('documents')=='Yes':
                documents=True
            else:
                documents=False
            
            if request.form.get('vulnerable_other_specify')=='Yes':
                vulnerable_other_specify=True
            else:
                vulnerable_other_specify=False

            # section 2.1
            if request.form.get('vulnerable_communities')=='Yes':
                vulnerable_communities=True
            else:
                vulnerable_communities=False

            if request.form.get('age_range')=='Yes':
                age_range=True
            else:
                age_range=False

            if request.form.get('uj_employees')=='Yes':
                uj_employees=True
            else:
                uj_employees=False

            if request.form.get('vulnerable')=='Yes':
                vulnerable=True
            else:
                vulnerable=False

            if request.form.get('non_english')=='Yes':
                non_english=True
            else:
                non_english=False

            if request.form.get('own_students')=='Yes':
                own_students=True
            else:
                own_students=False

            if request.form.get('poverty')=='Yes':
                poverty=True
            else:
                poverty=False
            
            if request.form.get('no_education')=='Yes':
                no_education=True
            else:
                no_education=False
            
            form.assessment_other_specify=request.form.get('assessment_other_specify')

            if request.form.get('vulnerable_comments_1')=='Yes':
                vulnerable_comments_1=True
            else:
                vulnerable_comments_1=False

            # 2.2
            if request.form.get('disclosure')=='Yes':
                disclosure=True
            else:
                disclosure=False

            if request.form.get('discomfiture')=='Yes':
                discomfiture=True
            else:
                discomfiture=False

            if request.form.get('deception')=='Yes':
                deception=True
            else:
                deception=False
            
            if request.form.get('sensitive')=='Yes':
                sensitive=True
            else:
                sensitive=False

            if request.form.get('prejudice')=='Yes':
                prejudice=True
            else:
                prejudice=False

            
            if request.form.get('intrusive_techniques')=='Yes':
                intrusive_techniques=True
            else:
                intrusive_techniques=False

            if request.form.get('illegal_activities')=='Yes':
                illegal_activities=True
            else:
                illegal_activities=False

            if request.form.get('personal')=='Yes':
                personal=True
            else:
                personal=False
                
            if request.form.get('available_records')=='Yes':
                available_records=True
            else:
                available_records=False

            if request.form.get('inventories')=='Yes':
                inventories=True
            else:
                inventories=False

            if request.form.get('risk_activities')=='Yes':
                risk_activities=True
            else:
                risk_activities=False

            if request.form.get('activity_specify')=='Yes':
                activity_specify=True
            else:
                activity_specify=False
            
            if request.form.get('vulnerable_comments_2')=='Yes':
                vulnerable_comments_2=True
            else:
                vulnerable_comments_2=False
            
            # Risk Assessment 2.3
            if request.form.get('incentives')=='Yes':
                incentives=True
            else:
                incentives=False

            if request.form.get('financial_costs')=='Yes':
                financial_costs=True
            else:
                financial_costs=False

            if request.form.get('reward')=='Yes':
                reward=True
            else:
                reward=False
            
            if request.form.get('conflict')=='Yes':
                conflict=True
            else:
                conflict=False

            if request.form.get('uj_premises')=='Yes':
                uj_premises=True
            else:
                uj_premises=False
    
            if request.form.get('uj_facilities')=='Yes':
                uj_facilities=True
            else:
                uj_facilities=False

            if request.form.get('uj_funding')=='Yes':
                uj_funding=True
            else:
                uj_funding=False
            
            form.vulnerable_comments_3=request.form.get('vulnerable_comments_3')
            
            if request.form.get('dataType') == 'public':
                    public_data_description = request.form.get('public_data_description')

            if request.form.get('researcher_affiliation')=='Yes':
                researcher_affiliation=True
            else:
                researcher_affiliation=False

            if request.form.get('collective_involvement')=='Yes':
                collective_involvement=True
            else:
                collective_involvement=False
        
            secondary_data = request.form.get('secondary_data')  # This should be added as a hidden input for access

            if secondary_data=='No':
                form.uses_secondary_data = False
            else:
                form.uses_secondary_data = True
                form.secondary_data_type = request.form.get('data_type')
                if form.secondary_data_type == 'private':
                    form.private_permission = request.form.get('privatePermission') == 'Yes'
                    # Handle file upload for permission if required
                    # Add logic for saving file securely if uploaded
                elif form.secondary_data_type == 'public':
                    form.public_data_description = request.form.get('public_data_description')
                
            
                
            if request.form.get('translator')=='Yes':
                translator=True
            else:
                translator=False

            if request.form.get('intervention')=='Yes':
                intervention=True
            else:
                intervention=False


            if request.form.get('use_focus_groups')=='Yes':
                use_focus_groups=True

            else:
                use_focus_groups=False


            if request.form.get('conflict_interest')=='Yes':
                conflict_interest=True
            else:
                conflict_interest=False

            
            data_nature=request.form.get('data_nature')
            data_origin=request.form.get('data_origin')
            access_conditions=request.form.get('access_conditions')
            personal_info=request.form.get('personal_info')
            personal_info_comment=request.form.get('personal_info_comment')
            data_anonymized=request.form.get('data_anonymized')
            anonymization_comment=request.form.get('anonymization_comment')
        
            permission_details=request.form.get('permission_details')
            public_data_description=request.form.get('public_data_description')
            shortcomings_reported=request.form.get('shortcomings_reported')
            limitations_reporting=request.form.get('limitations_reporting')
            methodology_alignment=request.form.get('methodology_alignment')
            data_acknowledgment=request.form.get('data_acknowledgment')

                # Handle file upload
            file = request.files.get('private_permission_file')
            if file and file.filename:
                    form.private_permission_file = file.read()
                    form.private_permission_filename = file.filename

            interviews_one = request.form.get('interviews') == 'Yes'
            documents_one = request.form.get('documents') == 'Yes'
            
            form.user_id=user_id
            form.attachment_id=form_requirements.id
            form.applicant_name=request.form.get('applicant_name')
            form.student_number=request.form.get('student_number')
            form.institution=request.form.get('institution')
            form.department=request.form.get('department')
            form.degree=request.form.get('degree')
            form.study_title=request.form.get('study_title')
            form.mobile=request.form.get('mobile')
            form.email=user.email
            form.supervisor=supervisor.full_name
            form.supervisor_email=supervisor.email
            form.survey=survey
            form.observations=observations
            form.focus_groups=focus_groups
            form.interviews=interviews
            form.documents=documents
            form.vulnerable_other_specify=vulnerable_other_specify
            form.vulnerable_communities=vulnerable_communities
            form.age_range=age_range
            form.uj_employees=uj_employees
            form.vulnerable=vulnerable
            form.non_english=non_english
            form.own_students=own_students
            form.poverty=poverty
            form.no_education=no_education
            form.assessment_other_specify=request.form.get('assessment_other_specify')
            form.vulnerable_comments_1=vulnerable_comments_1
            form.disclosure=disclosure
            form.discomfiture=discomfiture
            form.deception=deception
            form.sensitive=sensitive
            form.prejudice=prejudice
            form.intrusive_techniques=intrusive_techniques
            form.illegal_activities=illegal_activities
            form.personal=personal
            form.available_records=available_records
            form.inventories=inventories
            form.risk_activities=risk_activities
            form.activity_specify=activity_specify
            form.vulnerable_comments_2=vulnerable_comments_2
            form.incentives=incentives
            form.financial_costs=financial_costs
            form.reward=reward
            form.conflict=conflict
            form.uj_premises=uj_premises
            form.uj_facilities=uj_facilities
            form.uj_funding=uj_funding
            form.vulnerable_comments_3=request.form.get('vulnerable_comments_3')
            form.risk_rating = request.form.get('risk_rating')
            form.risk_justification = request.form.get('risk_justification')
            form.benefits_description = request.form.get('benefits_description')
            form.risk_mitigation = request.form.get('risk_mitigation')

            form.interviews_one = interviews_one
            form.documents_one = documents_one
            form.other_sec2 = request.form.get('other_sec2')
                # Section 3: Project Information
            form.title_provision = request.form.get('title_provision')
            form.abstract = request.form.get('abstract')
            form.questions = request.form.get('questions')
            form.purpose_objectives = request.form.get('purpose_objectives')

                # Section 4: Organisational Permissions and Affiliations
            form.grant_permission=request.form.get('grant_permission')
            form.org_name = ','.join(request.form.getlist('org_name[]'))
            form.org_contact = ','.join(request.form.getlist('org_contact[]'))
            form.org_role = ','.join(request.form.getlist('org_role[]'))
            form.org_permission=','.join(request.form.getlist('org_permission[]'))
                
            form.researcher_affiliation = 'Yes' if researcher_affiliation else 'No'
            form.affiliation_details = request.form.get('affiliation_details')

            form.collective_involvement = 'Yes' if collective_involvement else 'No'
                

            form.collective_details = request.form.get('collective_details')
                # Funding Information
            form.is_funded = request.form.get('is_funded')
            form.fund_org = ','.join(request.form.getlist('fund_org[]'))
            form.fund_contact = ','.join(request.form.getlist('fund_contact[]'))
            form.fund_role = ','.join(request.form.getlist('fund_role[]'))
            form.fund_amount =','.join(request.form.getlist('fund_amount[]'))

                # Indemnity & Other Committee Info
            form.indemnity_arrangements = request.form.get('indemnity_arrangements')
            form.other_committee = request.form.get('other_committee')

        
                # 5.1 Research Paradigm
            form.quantitative = "Yes" in request.form.getlist('quantitative[]')
            form.qualitative ="Yes" in request.form.getlist('qualitative[]')
            form.mixed_methods = "Yes" in request.form.getlist('mixed_methods[]')
            form.paradigm_explanation = request.form.get('paradigm_explanation')

                # 5.2 Research Design
            form.design = request.form.get('design')

                # 5.3 Participant Details
            form.participants_description = request.form.get('participants_description')
            form.population = ','.join(request.form.getlist('population[]'))
            form.sampling_method = ','.join(request.form.getlist('sampling_method[]'))
            form.sampling_size = ','.join(cleaned_sample_sizes)
            form.inclusion_criteria =','.join(request.form.getlist('inclusion_criteria[]'))
            form.duration_timing = request.form.get('duration_timing')
            form.contact_details_method = request.form.get('contact_details_method')
            form.conflict_interest = conflict_interest
            form.conflict_explanation = request.form.get('conflict_explanation')

                # 5.4 Instruments
            form.questionnaire_type = request.form.get('questionnaire_type')
            questionnaire_permission = request.form.get('questionnaire_permission')
            if questionnaire_permission is not None:
                questionnaire_permission = questionnaire_permission.strip()
                if questionnaire_permission == 'Yes':
                    form.permission_obtained = 'Yes'
                    form.open_source = 'No'
                elif questionnaire_permission == 'Open Source':
                    form.permission_obtained = 'No'
                    form.open_source = 'Yes'
                else:
                    form.permission_obtained = None
                    form.open_source = None
            else:
                form.permission_obtained = request.form.get('permission_obtained')
                form.open_source = request.form.get('open_source')
            form.instrument_attachment_reason = request.form.get('instrument_attachment_reason')
            form.data_collection_procedure = request.form.get('data_collection_procedure')
            form.interview_type = request.form.get('interview_type')
            form.interview_recording = request.form.get('interview_recording')
            form.use_focus_groups = use_focus_groups
            form.focus_recording = request.form.get('focus_recording')
            form.observation_details = request.form.get('observation_details')
            form.documents_details = request.form.get('documents_details')
            form.other_details = request.form.get('other_details')
            form.data_collectors = request.form.get('data_collectors')
            form.data_methods=','.join(request.form.getlist('data_methods[]'))
                #in_depth=request.form.get("in_depth"),
                #semi_structured=request.form.get("semi_structured"),
                #unstructured=request.form.get("unstructured"),
            form.intervention =intervention
            form.intervention_details = request.form.get('intervention_details')
            form.sensitive_data = request.form.get('sensitive_data')
            form.translator = translator
            form.translator_procedure = request.form.get('translator_procedure')

                # 5.5 Secondary Data Usage
            form.data_nature=data_nature
            form.data_origin=data_origin
            form.access_conditions=access_conditions
            form.personal_info=personal_info
            form.personal_info_comment=personal_info_comment
            form.data_anonymized=data_anonymized
            form.anonymization_comment=anonymization_comment
            form.permission_details=permission_details
            form.shortcomings_reported=shortcomings_reported
            form.limitations_reporting=limitations_reporting
            form.methodology_alignment=methodology_alignment
            form.data_acknowledgment=data_acknowledgment
            form.private_permission= request.form.get('privatePermission')
            form.public_data_description=public_data_description
            form.informed_consent=request.form.get('informed_consent')
            form.secure_location=','.join(request.form.getlist('secure_location[]'))
            form.password_protected=','.join(request.form.getlist('password_protected[]'))
            form.protected_place=','.join(request.form.getlist('protected_place[]'))
            form.retention=','.join(request.form.getlist('retention[]'))
            form.data_storage=','.join(request.form.getlist('data_storage[]'))
            form.study_benefits=request.form.get('study_benefits')
            form.participant_risks=request.form.get('participant_risks')
            form.adverse_steps=request.form.get('adverse_steps')
            form.community_participation=request.form.get('community_participation')
            form.community_effects=request.form.get('community_effects')
                #remove_identifiers=request.form.getlist("remove_identifiers"),
                #encryption=request.form.getlist("encryption"),
                #pseudonyms=request.form.getlist("pseudonyms"),
                #focus_group_warning=request.form.getlist("focus_group_warning"),
            form.privacy=','.join(request.form.getlist('privacy[]'))
            form.q6_9a= request.form.get("q6_9a")=='yes'
            form.q6_9b=request.form.get("q6_9b")=='yes'
            form.q6_9c=request.form.get("q6_9c")=='yes'
            form.q6_9d=request.form.get("q6_9d")=='yes'
            form.q6_9e=request.form.get("q6_9e")=='yes'
            form.q6_9f=request.form.get("q6_9f")=='yes'
            form.q6_9g=request.form.get("q6_9g")=='yes'
            form.q6_9h=request.form.get("q6_9h")=='yes'
            form.q6_9i=request.form.get("q6_9i")=='yes'
            form.q6_9j=request.form.get("q6_9j")=='yes'
            form.q6_9k=request.form.get("q6_9k")=='yes'
            form.q6_9l=request.form.get("q6_9l")=='yes'
            form.q6_9m=request.form.get("q6_9m")=='yes'
            form.q6_9n=request.form.get("q6_9n")=='yes'
            form.q6_9o=request.form.get("q6_9o")=='yes'
            form.q6_9p=request.form.get("q6_9p")=='yes'
            form.q6_9q=request.form.get("q6_9q")=='yes'
            form.q6_9r=request.form.get("q6_9r")=='yes'
            form.q6_9s=request.form.get("q6_9s")=='yes'
            form.results_feedback=request.form.get('results_feedback')
            form.products_access=request.form.get('products_access')
            form.publication_plans=request.form.get('publication_plans')
            form.participant_comp=request.form.get('participant_comp')
            form.participant_costs=request.form.get('participant_costs')
            form.ethics_reporting=request.form.get('ethics_reporting')
            

            # Handle file upload
            file = request.files.get('private_permission_file')
            if file and file.filename:
                form.private_permission_file = file.read()
                form.private_permission_filename = file.filename
    
            db_session.add(form)
            db_session.commit()
         
            return redirect(url_for('student_dashboard'))
        except Exception as e:
            db_session.rollback()
            flash(f"Error saving Form A: {str(e)}", "danger")
            print("Exception in FormA save:", e)
            import traceback; traceback.print_exc()
            return render_template("student_continue_forma.html",formA=form,data_org=data_org,data_fund=data_fund,data_sampling=data_sampling)
    return render_template("student_continue_forma.html",formA=form,data_org=data_org,data_fund=data_fund,data_sampling=data_sampling)


@app.route('/submit_form_a/<string:form_id>',methods=['GET','POST'])
def submit_form_a(form_id):
    """
    Submit form to supervisor - saves ALL sections including Section 7 and marks as submitted
    """
    print(f"DEBUG submit_form_a called: form_id={form_id}, method={request.method}")
    
    user_id=session.get('id')

    public_data_description=""
    private_permission_file=None
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    user = db_session.query(User).filter(User.user_id == user_id).first()
    supervisor=db_session.query(User).filter(User.user_id == user.supervisor_id).first()
    
    # Resolve the draft to submit. Never create a new row at submit time,
    # otherwise a stale/missing form_id can produce duplicate records.
    form = db_session.query(FormA).filter(FormA.user_id==user_id, FormA.form_id==form_id).first()
    form_exists = form is not None

    if not form_exists:
        # Fallback to the latest unsubmitted draft for this user.
        form = (
            db_session.query(FormA)
            .filter(FormA.user_id == user_id, FormA.submitted_at.is_(None))
            .order_by(FormA.created_at.desc())
            .first()
        )
        if not form:
            flash("No draft Form A found to submit. Please open your draft and try again.", "warning")
            return redirect(url_for('student_continue_forma'))
   
    form_requirements = db_session.query(FormARequirements).filter(FormARequirements.user_id == user_id).first()
    
    if request.method=='POST':
        submitted_at=get_local_time()
        declaration_name = request.form.get('declaration_name')
        applicant_signature = request.form.get('applicant_signature')
        declaration_date=get_local_time()
        was_in_corrections = is_student_correction_state(form)
        cleaned_sample_sizes, sample_size_error = _normalize_sampling_size_list(request.form.getlist('sample_size[]'))
        
        print(f"DEBUG submit_form_a: declaration_name={declaration_name}, applicant_signature={applicant_signature}")
        print(f"DEBUG submit_form_a: form_id={form_id}, form_exists={form_exists}")
        
        # Validate Section 7 is complete
        if not (declaration_name and applicant_signature):
            flash("Please complete all Section 7 (Declaration) fields before submitting.", "error")
            return redirect(url_for('student_continue_forma', form_id=form_id))
        if sample_size_error:
            flash(sample_size_error, "danger")
            return redirect(url_for('student_continue_forma', form_id=form_id))
        
        # First, call the same processing logic as student_continue_forma to save all sections
        # This ensures all data from the form is saved before marking as submitted
        
        # Helper function to convert checkbox values to boolean
        def to_bool(value):
            if isinstance(value, bool):
                return value
            if value is None:
                return False
            if isinstance(value, str):
                return value.lower() in ('yes', 'on', 'true', '1')
            return bool(value)
        
        try:
            # Process all the form data (reuse logic from student_continue_forma)
            # Convert checkboxes
            survey = to_bool(request.form.get('survey'))
            focus_groups = to_bool(request.form.get('focus_groups'))
            observations = to_bool(request.form.get('observations'))
            interviews = to_bool(request.form.get('interviews'))
            documents = to_bool(request.form.get('documents'))
            vulnerable_other_specify = to_bool(request.form.get('vulnerable_other_specify'))
            vulnerable_communities = to_bool(request.form.get('vulnerable_communities'))
            age_range = to_bool(request.form.get('age_range'))
            uj_employees = to_bool(request.form.get('uj_employees'))
            vulnerable = to_bool(request.form.get('vulnerable'))
            non_english = to_bool(request.form.get('non_english'))
            own_students = to_bool(request.form.get('own_students'))
            poverty = to_bool(request.form.get('poverty'))
            no_education = to_bool(request.form.get('no_education'))
            vulnerable_comments_1 = to_bool(request.form.get('vulnerable_comments_1'))
            disclosure = to_bool(request.form.get('disclosure'))
            discomfiture = to_bool(request.form.get('discomfiture'))
            deception = to_bool(request.form.get('deception'))
            sensitive = to_bool(request.form.get('sensitive'))
            prejudice = to_bool(request.form.get('prejudice'))
            intrusive_techniques = to_bool(request.form.get('intrusive_techniques'))
            illegal_activities = to_bool(request.form.get('illegal_activities'))
            personal = to_bool(request.form.get('personal'))
            available_records = to_bool(request.form.get('available_records'))
            inventories = to_bool(request.form.get('inventories'))
            risk_activities = to_bool(request.form.get('risk_activities'))
            activity_specify = to_bool(request.form.get('activity_specify'))
            vulnerable_comments_2 = to_bool(request.form.get('vulnerable_comments_2'))
            incentives = to_bool(request.form.get('incentives'))
            financial_costs = to_bool(request.form.get('financial_costs'))
            reward = to_bool(request.form.get('reward'))
            conflict = to_bool(request.form.get('conflict'))
            uj_premises = to_bool(request.form.get('uj_premises'))
            uj_facilities = to_bool(request.form.get('uj_facilities'))
            uj_funding = to_bool(request.form.get('uj_funding'))
            researcher_affiliation = to_bool(request.form.get('researcher_affiliation'))
            collective_involvement = to_bool(request.form.get('collective_involvement'))
            
            secondary_data = request.form.get('secondary_data')
            if secondary_data == 'No':
                form.uses_secondary_data = False
            else:
                form.uses_secondary_data = True
                form.secondary_data_type = request.form.get('data_type')
                if form.secondary_data_type == 'private':
                    form.private_permission = to_bool(request.form.get('privatePermission'))
                    file = request.files.get('private_permission_file')
                    if file and file.filename:
                        form.private_permission_file = file.read()
                        form.private_permission_filename = file.filename

            # Assign all form fields
            form.user_id = user_id
            form.attachment_id = form_requirements.id if form_requirements else None
            form.applicant_name = request.form.get('applicant_name')
            form.student_number = request.form.get('student_number')
            form.institution = request.form.get('institution')
            form.department = request.form.get('department')
            form.degree = request.form.get('degree')
            form.study_title = request.form.get('study_title')
            form.mobile = request.form.get('mobile')
            form.email = user.email
            form.supervisor = supervisor.full_name if supervisor else ''
            form.supervisor_email = supervisor.email if supervisor else ''
            
            # Section 2 fields
            form.survey = survey
            form.observations = observations
            form.focus_groups = focus_groups
            form.interviews = interviews
            form.documents = documents
            form.vulnerable_other_specify = vulnerable_other_specify
            form.vulnerable_communities = vulnerable_communities
            form.age_range = age_range
            form.uj_employees = uj_employees
            form.vulnerable = vulnerable
            form.non_english = non_english
            form.own_students = own_students
            form.poverty = poverty
            form.no_education = no_education
            form.assessment_other_specify = request.form.get('assessment_other_specify')
            form.vulnerable_comments_1 = vulnerable_comments_1
            form.disclosure = disclosure
            form.discomfiture = discomfiture
            form.deception = deception
            form.sensitive = sensitive
            form.prejudice = prejudice
            form.intrusive_techniques = intrusive_techniques
            form.illegal_activities = illegal_activities
            form.personal = personal
            form.available_records = available_records
            form.inventories = inventories
            form.risk_activities = risk_activities
            form.activity_specify = activity_specify
            form.vulnerable_comments_2 = vulnerable_comments_2
            form.incentives = incentives
            form.financial_costs = financial_costs
            form.reward = reward
            form.conflict = conflict
            form.uj_premises = uj_premises
            form.uj_facilities = uj_facilities
            form.uj_funding = uj_funding
            form.vulnerable_comments_3 = request.form.get('vulnerable_comments_3')
            form.risk_rating = request.form.get('risk_rating')
            form.risk_justification = request.form.get('risk_justification')
            form.benefits_description = request.form.get('benefits_description')
            form.risk_mitigation = request.form.get('risk_mitigation')
            form.interviews_one = to_bool(request.form.get('interviews'))
            form.documents_one = to_bool(request.form.get('documents'))
            form.other_sec2 = request.form.get('other_sec2')
            
            # Section 3
            form.title_provision = request.form.get('title_provision')
            form.abstract = request.form.get('abstract')
            form.questions = request.form.get('questions')
            form.purpose_objectives = request.form.get('purpose_objectives')

            # Section 4
            form.grant_permission = request.form.get('grant_permission')
            form.org_name = ','.join(request.form.getlist('org_name[]'))
            form.org_contact = ','.join(request.form.getlist('org_contact[]'))
            form.org_role = ','.join(request.form.getlist('org_role[]'))
            form.org_permission = ','.join(request.form.getlist('org_permission[]'))
            form.researcher_affiliation = 'Yes' if researcher_affiliation else 'No'
            form.affiliation_details = request.form.get('affiliation_details')
            form.collective_involvement = 'Yes' if collective_involvement else 'No'
            form.collective_details = request.form.get('collective_details')
            form.is_funded = request.form.get('is_funded')
            form.fund_org = ','.join(request.form.getlist('fund_org[]'))
            form.fund_contact = ','.join(request.form.getlist('fund_contact[]'))
            form.fund_role = ','.join(request.form.getlist('fund_role[]'))
            form.fund_amount = ','.join(request.form.getlist('fund_amount[]'))
            form.indemnity_arrangements = request.form.get('indemnity_arrangements')
            form.other_committee = request.form.get('other_committee')

            # Section 5
            form.quantitative = "Yes" in request.form.getlist('quantitative[]') or to_bool(request.form.get('quantitative'))
            form.qualitative = "Yes" in request.form.getlist('qualitative[]') or to_bool(request.form.get('qualitative'))
            form.mixed_methods = "Yes" in request.form.getlist('mixed_methods[]') or to_bool(request.form.get('mixed_methods'))
            form.paradigm_explanation = request.form.get('paradigm_explanation')
            form.population = ','.join(request.form.getlist('population[]'))
            form.sampling_method = ','.join(request.form.getlist('sampling_method[]'))
            form.sampling_size = ','.join(cleaned_sample_sizes)
            form.inclusion_criteria = ','.join(request.form.getlist('inclusion_criteria[]'))
            form.translator = to_bool(request.form.get('translator'))
            form.translator_details = request.form.get('translator_details')
            form.intervention = to_bool(request.form.get('intervention'))
            form.intervention_details = request.form.get('intervention_details')
            form.personal_info = to_bool(request.form.get('personal_info'))
            form.personal_info_comment = request.form.get('personal_info_comment')
            form.conflict_interest = to_bool(request.form.get('conflict_interest'))
            form.conflict_explanation = request.form.get('conflict_explanation')
            
            # Method checkboxes
            form.questionnaire = 'questionnaire' in request.form.getlist('method[]')
            form.interview = 'interview' in request.form.getlist('method[]')
            form.focus = 'focus' in request.form.getlist('method[]')
            form.observation = 'observation' in request.form.getlist('method[]')
            form.documents_method = 'documents' in request.form.getlist('method[]')
            form.other_method = 'other' in request.form.getlist('method[]')
            form.questionnaire_explain = request.form.get('questionnaire_explain')
            form.interview_explain = request.form.get('interview_explain')
            form.focus_explain = request.form.get('focus_explain')
            form.observation_explain = request.form.get('observation_explain')
            form.documents_explain = request.form.get('documents_explain')
            form.other_explain = request.form.get('other_explain')
            form.data_public = request.form.get('data_public')
            form.public_data_link = request.form.get('public_data_link')
            
            # Section 6
            form.procedures = request.form.get('procedures')
            form.anonymity_confidentiality = request.form.get('anonymity_confidentiality')
            form.data_storage_security = request.form.get('data_storage_security')
            form.informed_consent = request.form.get('informed_consent')
            form.voluntary_participation = request.form.get('voluntary_participation')
            form.products_access = request.form.get('products_access')
            form.publication_plans = request.form.get('publication_plans')
            form.participant_comp = request.form.get('participant_comp')
            form.participant_costs = request.form.get('participant_costs')
            form.ethics_reporting = request.form.get('ethics_reporting')

            # Section 7 - Mark as submitted
            form.submitted_at = submitted_at
            form.declaration_name = declaration_name
            form.applicant_signature = applicant_signature
            form.declaration_date = declaration_date
            form.submitted = True
            form.rejected_or_accepted = False
            form.status = 'Resubmitted' if was_in_corrections else 'Submitted'
            form.visible_to_student = False
            form.ethics_form_status = 'Resubmitted' if was_in_corrections else 'Submitted'
            form.form_supervisor_status = 'Resubmitted' if was_in_corrections else 'Submitted'
            reset_form_review_feedback(form)
            
            print(f"DEBUG: About to commit form - declaration_name={form.declaration_name}, submitted={form.submitted}")

            db_session.add(form)
            db_session.commit()
            
            print(f"DEBUG: Form committed successfully - form_id={form.form_id}")

            # Send notifications
            try:
                message = 'You have successfully edited and submitted your form. Please wait while its under review.'
                send_email(app, mail, message, [user.email])
                messages = f'{form.applicant_name} has submitted a form that needs to be reviewed.'
                send_email(app, mail, messages, [form.supervisor_email])
            except Exception as e:
                app.logger.error(f"Failed to send email to {form.supervisor_email}: {e}")
            
            flash("Form successfully submitted to supervisor!", "success")
            return redirect(url_for('student_dashboard'))
            
        except Exception as e:
            db_session.rollback()
            print(f"ERROR in submit_form_a: {str(e)}")
            print(f"ERROR traceback: {traceback.format_exc()}")
            app.logger.error(f"Error submitting form: {e}")
            flash(f"An error occurred while submitting the form: {str(e)}", "error")
            return redirect(url_for('student_continue_forma', form_id=form_id))


    data_org={
        "org_name" : parse_field(form.org_name),
        "org_contact" : parse_field(form.org_contact),
        "org_role": parse_field(form.org_role),
        "org_permission" : parse_field(form.org_permission),
    }
    data_fund={
        "fund_org" : parse_field(form.fund_org),
        "fund_contact" :parse_field(form.fund_contact),
        "fund_role": parse_field(form.fund_role),
        "fund_amount": parse_field(form.fund_amount),
    }
    data_sampling={
        "population" :parse_field(form.population),
        "sampling_method" : parse_field(form.sampling_method),
        "sampling_size": parse_field(form.sampling_size),
        "inclusion_criteria": parse_field(form.inclusion_criteria)
    } 

    return render_template("student_continue_forma.html",formA=form,data_org=data_org,data_fund=data_fund,data_sampling=data_sampling)



@app.route('/student_edit_formb', methods=['GET','POST'])
def student_edit_formb():
    user_id=session.get('id')

    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    user = db_session.query(User).filter(User.user_id == user_id).first()
    supervisor=db_session.query(User).filter(User.user_id == user.supervisor_id).first()
    form = db_session.query(FormB).options(
        defer(FormB.permission_letter),
        defer(FormB.prior_clearance),
        defer(FormB.ethics_evidence),
        defer(FormB.proposal_path),
        defer(FormB.pending_note),
        defer(FormB.private_permission_file)
    ).filter_by(user_id=user_id).order_by(FormB.submitted_at.desc().nullslast(), FormB.created_at.desc().nullslast()).first()

    locked_response = redirect_if_student_form_locked(form, 'Form B')
    if locked_response:
        return locked_response
    
    if request.method=="POST":
        print("[DEBUG] FormB POST request received")
        data_public= request.form.get('data_public')=='Yes'
        personal_info=request.form.get('personal_info')== 'Yes'
        private_permission=request.form.get('private_permission')=='Yes'
        shortcomings_reported=request.form.get('shortcomings_reported')=="Yes"
        methodology_alignment=request.form.get('methodology_alignment')=="Yes"
        declaration_name = (request.form.get('declaration_name') or request.form.get('applicant_name')).strip()
        applicant_signature = (request.form.get('applicant_signature') or '').strip()
        print(f"[DEBUG] declaration_name: {declaration_name}, applicant_signature: {applicant_signature}")
        if not declaration_name or not applicant_signature:
            print("[DEBUG] Declaration fields missing, redirecting.")
            flash('Declaration section must be completed to submit the form', 'warning')
            return redirect(url_for('student_edit_formb'))
        if not form:
            form = FormB(user_id=user_id)
            inherit_previous_reviewers(form, FormB, user_id, FormB.submitted_at)
            db_session.add(form)
            print("[DEBUG] FormB instance created and added to session.")
        form.applicant_name=request.form.get('applicant_name')
        form.student_number=request.form.get('student_number')
        form.institution=request.form.get('institution')
        form.department=request.form.get('department')
        form.degree=request.form.get('degree')
        form.study_title=request.form.get('study_title')
        form.mobile=request.form.get('mobile')
        form.email=user.email
        form.supervisor=supervisor.full_name
        form.supervisor_email=supervisor.email
        form.project_description = request.form.get('project_description')
        form.data_nature = request.form.get('data_nature')
        form.data_origin = request.form.get('data_origin')
        form.data_public=data_public
        form.personal_info=personal_info
        form.public_evidence = request.form.get('public_evidence')
        form.access_conditions = request.form.get('access_conditions')
        form.private_permission=private_permission
        form.data_anonymized = request.form.get('data_anonymized')
        form.anonymization_comment = request.form.get('anonymization_comment')
        form.shortcomings_reported=shortcomings_reported
        form.methodology_alignment=methodology_alignment
        form.permission_details = request.form.get('permission_details')
        form.limitations_reporting = request.form.get('limitations_reporting')
        form.original_clearance=request.form.get('original_clearance')
        form.participant_permission=request.form.get('participant_permission')
        form.data_safekeeping=request.form.get('data_safekeeping')
        form.risk_level=request.form.get('risk_level')
        form.risk_comments=request.form.get('risk_comments')
        form.declaration_name=declaration_name
        form.applicant_signature=applicant_signature
        form.full_name=(request.form.get('full_name') or request.form.get('applicant_name')).strip()
        form.submitted_at = get_local_time()
        form.declaration_date = get_local_time()
        form.submitted = True
        form.rejected_or_accepted = False
        was_in_corrections = is_student_correction_state(form)
        form.status = 'Resubmitted' if was_in_corrections else (form.status or 'Submitted')
        form.visible_to_student = False
        form.ethics_form_status = 'Resubmitted' if was_in_corrections else (form.ethics_form_status or 'Submitted')
        form.form_supervisor_status = 'Resubmitted' if was_in_corrections else (form.form_supervisor_status or 'Submitted')
        reset_form_review_feedback(form)
        # Handle file upload
        file = request.files.get('private_permission_file')
        if file and file.filename:
            print(f"[DEBUG] File uploaded: {file.filename}")
            form.private_permission_file = file.read()
            form.private_permission_filename = file.filename
        import traceback
        try:
            db_session.commit()
            print("[DEBUG] FormB committed successfully.")
        except Exception as e:
            db_session.rollback()
            print(f"[DEBUG] FormB commit failed: {e}")
            traceback.print_exc()
            flash("An error occurred while submitting Form B. Please try again.", "danger")
            return redirect(url_for('student_edit_formb'))
        flash("Form B submitted successfully.", "success")
        return redirect(url_for('student_dashboard'))
    return render_template("student_edit_formb.html",formB=form)


@app.route('/student_continue_formb', methods=['GET','POST'])
def student_continue_formb():
    user_id=session.get('id')
    
    formA = db_session.query(FormA).filter_by(user_id=user_id).first()
    if formA:
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))
        
    formC = db_session.query(FormC).filter_by(user_id=user_id).first()
    if formC:
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))
    

    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    user = db_session.query(User).filter(User.user_id == user_id).first()
    supervisor=db_session.query(User).filter(User.user_id == user.supervisor_id).first()
    
    form = db_session.query(FormB).options(
        defer(FormB.permission_letter),
        defer(FormB.prior_clearance),
        defer(FormB.ethics_evidence),
        defer(FormB.proposal_path),
        defer(FormB.pending_note),
        defer(FormB.private_permission_file)
    ).filter(
        FormB.user_id == user_id,
        FormB.submitted_at.is_(None)
    ).order_by(FormB.created_at.desc().nullslast()).first()

    if form is None:
        form = db_session.query(FormB).options(
            defer(FormB.permission_letter),
            defer(FormB.prior_clearance),
            defer(FormB.ethics_evidence),
            defer(FormB.proposal_path),
            defer(FormB.pending_note),
            defer(FormB.private_permission_file)
        ).filter_by(user_id=user_id).order_by(FormB.submitted_at.desc().nullslast(), FormB.created_at.desc().nullslast()).first()

    # Ensure there is a draft instance before processing POST payload.
    if form is None:
        form = FormB(user_id=user_id)
        inherit_previous_reviewers(form, FormB, user_id, FormB.submitted_at)
        db_session.add(form)

    locked_response = redirect_if_student_form_locked(form, 'Form B')
    if locked_response:
        return locked_response

    if request.method=="POST":
        try:
            data_public= request.form.get('data_public')=='Yes'
            personal_info=request.form.get('personal_info')== 'Yes'
            private_permission=request.form.get('private_permission')=='Yes'
            shortcomings_reported=request.form.get('shortcomings_reported')=="Yes"
            methodology_alignment=request.form.get('methodology_alignment')=="Yes"
                        
            
            form.user_id=user_id
            form.applicant_name=request.form.get('applicant_name')
            form.student_number=request.form.get('student_number')
            form.institution=request.form.get('institution')
            form.department=request.form.get('department')
            form.degree=request.form.get('degree')
            form.study_title=request.form.get('study_title')
            form.mobile=request.form.get('mobile')
            form.email=user.email
            form.supervisor=supervisor.full_name
            form.supervisor_email=supervisor.email
            form.project_description = request.form.get('project_description')
            form.data_nature = request.form.get('data_nature')
            form.data_origin = request.form.get('data_origin')
            form.data_public=data_public
            form.personal_info=personal_info

            form.public_evidence = request.form.get('public_evidence')
            form.access_conditions = request.form.get('access_conditions')
            form.data_acknowledgment = request.form.get('data_acknowledgment')
            form.private_permission=private_permission

            form.data_anonymized = request.form.get('data_anonymized')
            form.anonymization_comment = request.form.get('anonymization_comment')

            form.shortcomings_reported=shortcomings_reported
            form.methodology_alignment=methodology_alignment

            form.permission_details = request.form.get('permission_details')
            
            # Handle file upload
            file = request.files.get('private_permission_file')
            if file and file.filename:
                form.private_permission_file = file.read()
                form.private_permission_filename = file.filename 

            form.limitations_reporting = request.form.get('limitations_reporting')

                    
            form.original_clearance=request.form.get('original_clearance')
            form.participant_permission=request.form.get('participant_permission')
            form.data_safekeeping=request.form.get('data_safekeeping')
            form.risk_level=request.form.get('risk_level')
            form.risk_comments=request.form.get('risk_comments')
            
            db_session.add(form)
            db_session.commit()
            return redirect(url_for('student_continue_formb'))
        except Exception as e:
            db_session.rollback()
            flash(f"Error saving Form A: {str(e)}", "danger")
            print("Exception in FormA save:", e)
            import traceback; traceback.print_exc()
            return render_template("student_continue_formb.html",formB=form)
        
    return render_template("student_continue_formb.html",formB=form)


@app.route('/submit_form_b/<string:form_id>',methods=['GET','POST'])
def submit_form_b(form_id):
    """
    Submit Form B to supervisor - saves ALL sections including Section 5 and marks as submitted
    """
    user_id=session.get('id')
    
    formA = db_session.query(FormA).filter_by(user_id=user_id).first()
    if formA:
        flash("You are not permitted to fill this form (FormA exists)", "warning")
        print(f"[ERROR] User {user_id} attempted to submit FormB but FormA exists.")
        return redirect(url_for("student_dashboard"))
    formC = db_session.query(FormC).filter_by(user_id=user_id).first()
    if formC:
        flash("You are not permitted to fill this form (FormC exists)", "warning")
        print(f"[ERROR] User {user_id} attempted to submit FormB but FormC exists.")
        return redirect(url_for("student_dashboard"))
    

    if not user_id:
        print(f"[ERROR] Unauthorized access to submit_form_b. No user_id in session.")
        flash("Unauthorized access. Please log in again.", "danger")
        return jsonify({'error': 'Unauthorized'}), 401
    user = db_session.query(User).filter(User.user_id == user_id).first()
    supervisor=db_session.query(User).filter(User.user_id == user.supervisor_id).first()
    
    # Check if form exists in database - if yes UPDATE (add declaration), if no CREATE with declaration
    form = db_session.query(FormB).filter(FormB.user_id==user_id, FormB.form_id==form_id).first()
    if not form:
        form = (
            db_session.query(FormB)
            .filter(FormB.user_id == user_id, FormB.submitted_at.is_(None))
            .order_by(FormB.created_at.desc())
            .first()
        )
        if not form:
            print(f"[ERROR] FormB draft not found for user_id={user_id}, form_id={form_id}")
            flash("No draft Form B found to submit. Please open your draft and try again.", "warning")
            return redirect(url_for('student_continue_formb'))

    locked_response = redirect_if_student_form_locked(form, 'Form B')
    if locked_response:
        return locked_response
   
    
    if request.method=='POST':
        print(f"[DEBUG] POST request received for submit_form_b by user_id={user_id}, form_id={form_id}")
        declaration_name=request.form.get('declaration_name')
        full_name=request.form.get('full_name')
        declaration_date = get_local_time()
        submitted_at=get_local_time()
        print(f"[DEBUG] Declaration: name={declaration_name}, full_name={full_name}, date={declaration_date}, submitted_at={submitted_at}")
        # Validate Section 5 (Declaration) is complete
        if not (declaration_name and full_name):
            print(f"[ERROR] Declaration fields missing for user_id={user_id}, form_id={form_id}. declaration_name={declaration_name}, full_name={full_name}")
            flash("Please complete all Section 5 (Declaration) fields before submitting.", "error")
            return redirect(url_for('student_continue_formb', form_id=form_id))
        
        # Helper function to convert checkbox values to boolean
        def to_bool(value):
            if isinstance(value, bool):
                return value
            if value is None:
                return False
            if isinstance(value, str):
                return value.lower() in ('yes', 'on', 'true', '1')
            return bool(value)
        
        try:
            print("[DEBUG] Processing form submission...")
            # Process all form data (same as student_continue_formb)
            data_public = to_bool(request.form.get('data_public'))
            personal_info = to_bool(request.form.get('personal_info'))
            private_permission = to_bool(request.form.get('private_permission'))
            shortcomings_reported = to_bool(request.form.get('shortcomings_reported'))
            methodology_alignment = to_bool(request.form.get('methodology_alignment'))
            
            # Assign all form fields
            form.user_id = user_id
            form.applicant_name = request.form.get('applicant_name')
            form.student_number = request.form.get('student_number')
            form.institution = request.form.get('institution')
            form.department = request.form.get('department')
            form.degree = request.form.get('degree')
            form.study_title = request.form.get('study_title')
            form.mobile = request.form.get('mobile')
            form.email = user.email
            form.supervisor = supervisor.full_name if supervisor else ''
            form.supervisor_email = supervisor.email if supervisor else ''
            form.project_description = request.form.get('project_description')
            form.data_nature = request.form.get('data_nature')
            form.data_origin = request.form.get('data_origin')
            form.data_public = data_public
            form.personal_info = personal_info
            form.public_evidence = request.form.get('public_evidence')
            form.access_conditions = request.form.get('access_conditions')
            form.data_acknowledgment = request.form.get('data_acknowledgment')
            form.private_permission = private_permission
            form.data_anonymized = request.form.get('data_anonymized')
            form.anonymization_comment = request.form.get('anonymization_comment')
            form.shortcomings_reported = shortcomings_reported
            form.methodology_alignment = methodology_alignment
            form.permission_details = request.form.get('permission_details')
            
            # Handle file upload
            file = request.files.get('private_permission_file')
            if file and file.filename:
                form.private_permission_file = file.read()
                form.private_permission_filename = file.filename
            
            form.limitations_reporting = request.form.get('limitations_reporting')
            form.original_clearance = request.form.get('original_clearance')
            form.participant_permission = request.form.get('participant_permission')
            form.data_safekeeping = request.form.get('data_safekeeping')
            form.risk_level = request.form.get('risk_level')
            form.risk_comments = request.form.get('risk_comments')
            
            # Section 5 - Mark as submitted
            form.declaration_name = (request.form.get('declaration_name') or request.form.get('applicant_name')).strip()
            form.full_name = (request.form.get('full_name') or request.form.get('applicant_name')).strip()
            form.declaration_date = declaration_date
            form.submitted_at = submitted_at
            form.submitted = True
            form.rejected_or_accepted = False
            was_in_corrections = is_student_correction_state(form)
            form.status = 'Resubmitted' if was_in_corrections else 'Submitted'
            form.ethics_form_status = 'Resubmitted' if was_in_corrections else 'Submitted'
            form.form_supervisor_status = 'Resubmitted' if was_in_corrections else 'Submitted'
            reset_form_review_feedback(form)
            print(f"[DEBUG] FormB updated: declaration_name={form.declaration_name}, full_name={form.full_name}, declaration_date={form.declaration_date}, submitted_at={form.submitted_at}")
            
            db_session.add(form)
            db_session.commit()
            print(f"[DEBUG] FormB committed successfully: form_id={form.form_id}")
            
            # Send notifications
            try:
                message = 'You have successfully edited and submitted your form. Please wait while its under review.'
                print(f"[DEBUG] Sending email to user: {user.email}")
                send_email(app, mail, message, [user.email])
                messages = f'{form.applicant_name} has submitted a form that needs to be reviewed.'
                print(f"[DEBUG] Sending email to supervisor: {form.supervisor_email}")
                send_email(app, mail, messages, [form.supervisor_email])
            except Exception as e:
                print(f"[DEBUG] Failed to send email to {form.supervisor_email}: {e}")
                app.logger.error(f"Failed to send email to {form.supervisor_email}: {e}")
            
            print("[DEBUG] Form successfully submitted to supervisor!")
            flash("Form successfully submitted to supervisor!", "success")
            print(f"[REDIRECT] Redirecting user_id={user_id} to student_dashboard after successful submission.")
            return redirect(url_for('student_dashboard'))
            
        except Exception as e:
            db_session.rollback()
            print(f"[ERROR] Exception during FormB submission for user_id={user_id}, form_id={form_id}: {e}")
            import traceback; traceback.print_exc()
            app.logger.error(f"Error submitting Form B: {e}")
            flash(f"An error occurred while submitting the form: {e}", "error")
            return redirect(url_for('submit_form_b', form_id=form_id))
    print(f"[DEBUG] Non-POST request to submit_form_b for user_id={user_id}, form_id={form_id}")
    return redirect(url_for('student_continue_formb'))



@app.route('/student_edit_formc', methods=['GET','POST'])
def student_edit_formc():
    user_id=session.get('id')
    
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    user = db_session.query(User).filter(User.user_id == user_id).first()
    supervisor=db_session.query(User).filter(User.user_id == user.supervisor_id).first()
    form = db_session.query(FormC).filter_by(user_id=user_id).order_by(FormC.submission_date.desc().nullslast(), FormC.created_at.desc().nullslast()).first()

    locked_response = redirect_if_student_form_locked(form, 'Form C')
    if locked_response:
        return locked_response
    if request.method=="POST":
        print("[DEBUG] FormC POST request received")
        declaration_name = (request.form.get('declaration_name') or request.form.get('applicant_name')).strip()
        full_name = (request.form.get('full_name') or request.form.get('applicant_name')).strip()
        submission_date = request.form.get('submission_date')
        print(f"[DEBUG] declaration_name: {declaration_name}, full_name: {full_name}, submission_date: {submission_date}")
        if not declaration_name or not full_name:
            print("[DEBUG] Declaration fields missing, redirecting.")
            flash('Declaration section must be completed to submit the form', 'warning')
            return redirect(url_for('student_edit_formc'))
        # Update existing form instance
        if not form:
            form = FormC(user_id=user_id)
            inherit_previous_reviewers(form, FormC, user_id, FormC.submission_date)
            db_session.add(form)
            print("[DEBUG] FormC instance created and added to session.")
        try:
            form.applicant_name=request.form.get('applicant_name')
            form.student_number=request.form.get('student_number')
            form.institution=request.form.get('institution')
            form.department=request.form.get('department')
            form.degree=request.form.get('degree')
            form.project_title=request.form.get('project_title')
            form.mobile_number=request.form.get('mobile_number')
            form.email_address=user.email
            form.supervisor_name=supervisor.full_name
            form.supervisor_email=supervisor.email
            form.vulnerable=True if request.form.get('vulnerable') else False
            form.age_under_18_or_over_65=True if request.form.get('age_under_18_or_over_65') else False
            form.uj_employees=True if request.form.get('uj_employees') else False
            form.non_vulnerable_context=True if request.form.get('non_vulnerable_context') else False
            form.non_english=True if request.form.get('non_english') else False
            form.own_students=True if request.form.get('own_students') else False
            form.poverty=True if request.form.get('poverty') else False
            form.no_education=True if request.form.get('no_education') else False
            form.vulnerable_other_description=True if request.form.get('vulnerable_other_description') else False
            form.vulnerable_comments=request.form.get('vulnerable_comments')
            form.consent_violation=True if request.form.get('consent_violation') else False
            form.discomfiture=True if request.form.get('discomfiture') else False
            form.deception=True if request.form.get('deception') else False
            form.sensitive_issues=True if request.form.get('sensitive_issues') else False
            form.prejudicial_info=True if request.form.get('prejudicial_info') else False
            form.intrusive=True if request.form.get('intrusive') else False
            form.illegal=True if request.form.get('illegal') else False
            form.direct_social_info=True if request.form.get('direct_social_info') else False
            form.identifiable_records=True if request.form.get('identifiable_records') else False
            form.psychology_tests=True if request.form.get('psychology_tests') else False
            form.researcher_risk=True if request.form.get('researcher_risk') else False
            form.activity_other_description=request.form.get('activity_other_description')
            form.activity_comments=request.form.get('activity_comments')
            form.incentives=True if request.form.get('incentives') else False
            form.participant_costs=True if request.form.get('participant_costs') else False
            form.researcher_interest=True if request.form.get('researcher_interest') else False
            form.conflict_of_interest=True if request.form.get('conflict_of_interest') else False
            form.uj_premises=True if request.form.get('uj_premises') else False
            form.uj_facilities=True if request.form.get('uj_facilities') else False
            form.uj_funding=True if request.form.get('uj_funding') else False
            form.consideration_comments=request.form.get('consideration_comments')
            form.risk_level=request.form.get('risk_level')
            form.risk_justification=request.form.get('risk_justification')
            form.risk_benefits=request.form.get('risk_benefits')
            form.risk_mitigation=request.form.get('risk_mitigation')
            form.summary_title=request.form.get('summary_title')
            form.executive_summary=request.form.get('executive_summary')
            form.research_questions=request.form.get('research_questions')
            form.research_purpose=request.form.get('research_purpose')
            form.secondary_data_info=request.form.get('secondary_data_info')
            form.exemption_reason=request.form.get('exemption_reason')
            form.declaration_name=declaration_name
            form.full_name=full_name
            form.submission_date=get_local_time()
            form.submitted = True
            form.rejected_or_accepted = False
            was_in_corrections = is_student_correction_state(form)
            form.status = 'Resubmitted' if was_in_corrections else (form.status or 'Submitted')
            form.visible_to_student = False
            form.ethics_form_status = 'Resubmitted' if was_in_corrections else (form.ethics_form_status or 'Submitted')
            form.form_supervisor_status = 'Resubmitted' if was_in_corrections else (form.form_supervisor_status or 'Submitted')
            reset_form_review_feedback(form)
            db_session.commit()
            print("[DEBUG] FormC committed successfully.")
            flash("Form C submitted successfully.", "success")
            return redirect(url_for('student_dashboard'))
        except Exception as e:
            db_session.rollback()
            print(f"[DEBUG] FormC commit failed: {e}")
            app.logger.error(f"Error submitting Form C: {e}")
            print(f"[DEBUG] Outer exception: {e}")
            flash("An error occurred while submitting the form. Please try again.", "error")
            return redirect(url_for('student_dashboard'))
    return render_template('student_edit_formc.html',formc=form)


@app.route('/student_continue_formc', methods=['GET','POST'])
def student_continue_formc():
    user_id=session.get('id')
    
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    formA = db_session.query(FormA).filter_by(user_id=user_id).first()
    if formA:
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))
        
    formB = db_session.query(FormB).filter_by(user_id=user_id).first()
    if formB:
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))
    

    user = db_session.query(User).filter(User.user_id == user_id).first()
    supervisor=db_session.query(User).filter(User.user_id == user.supervisor_id).first()
    
    form = db_session.query(FormC).filter(
        FormC.user_id == user_id,
        FormC.submission_date.is_(None)
    ).order_by(FormC.created_at.desc().nullslast()).first()

    if form is None:
        form = db_session.query(FormC).filter_by(user_id=user_id).order_by(FormC.submission_date.desc().nullslast(), FormC.created_at.desc().nullslast()).first()

    if form is None:
        form = FormC(user_id=user_id)
        inherit_previous_reviewers(form, FormC, user_id, FormC.submission_date)
        db_session.add(form)

    locked_response = redirect_if_student_form_locked(form, 'Form C')
    if locked_response:
        return locked_response
    
    if request.method=="POST":
        
        try:
            form.user_id=user_id
            form.applicant_name=request.form.get('applicant_name')
            form.student_number=request.form.get('student_number')
            form.institution=request.form.get('institution')
            form.department=request.form.get('department')
            form.degree=request.form.get('degree')
            form.project_title=request.form.get('project_title')
            form.mobile_number=request.form.get('mobile_number')
            form.email_address=user.email
            form.supervisor_name=supervisor.full_name
            form.supervisor_email=supervisor.email
            form.vulnerable=True if request.form.get('vulnerable') else False
                
            form.age_under_18_or_over_65=True if request.form.get('age_under_18_or_over_65') else False
            form.uj_employees=True if request.form.get('uj_employees') else False

            form.non_vulnerable_context=True if request.form.get('non_vulnerable_context') else False
            form.non_english=True if request.form.get('non_english')else False
            form.own_students=True if request.form.get('own_students') else False

            form.poverty=True if request.form.get('poverty') else False
            form.no_education=True if request.form.get('no_education') else False
            form.vulnerable_other_description=True if request.form.get('vulnerable_other_description') else False
            form.vulnerable_comments=request.form.get('vulnerable_comments')

            form.consent_violation=True if request.form.get('consent_violation') else False
            form.discomfiture=True if request.form.get('discomfiture') else False
            form.deception=True if request.form.get('deception') else False
            form.sensitive_issues=True if request.form.get('sensitive_issues') else False
            form.prejudicial_info=True if request.form.get('prejudicial_info') else False
            form.intrusive=True if request.form.get('intrusive') else False
            form.illegal=True if request.form.get('illegal') else False
            form.direct_social_info=True if request.form.get('direct_social_info') else False
            form.identifiable_records=True if request.form.get('identifiable_records') else False
            form.psychology_tests=True if request.form.get('psychology_tests') else False
            form.researcher_risk=True if request.form.get('researcher_risk') else False
            form.activity_other_description=request.form.get('activity_other_description')

            form.activity_comments=request.form.get('activity_comments')

            form.incentives=True if request.form.get('incentives') else False
            form.participant_costs=True if request.form.get('participant_costs') else False
            form.researcher_interest=True if request.form.get('researcher_interest') else False
            form.conflict_of_interest=True if request.form.get('conflict_of_interest') else False
            form.uj_premises=True if request.form.get('uj_premises') else False
            form.uj_facilities=True if request.form.get('uj_facilities') else False
            form.uj_funding=True if request.form.get('uj_funding') else False
            form.consideration_comments=request.form.get('consideration_comments')
                
            form.risk_level=request.form.get('risk_level')
            form.risk_justification=request.form.get('risk_justification')
            form.risk_benefits=request.form.get('risk_benefits')
            form.risk_mitigation=request.form.get('risk_mitigation')

            form.summary_title=request.form.get('summary_title')
            form.executive_summary=request.form.get('executive_summary')
            form.research_questions=request.form.get('research_questions')
            form.research_purpose=request.form.get('research_purpose')
            form.secondary_data_info=request.form.get('secondary_data_info')
            form.exemption_reason=request.form.get('exemption_reason')
            
            db_session.add(form)
            db_session.commit()
        except Exception as e:
            db_session.rollback()
            app.logger.error(f"Error submitting Form B: {e}")
            flash("An error occurred while submitting the form. Please try again.", "error")
            return redirect(url_for('student_dashboard'))
    return render_template('student_continue_formc.html',formc=form)




@app.route('/submit_form_c/<string:form_id>',methods=['GET','POST'])
def submit_form_c(form_id):
    """
    Submit Form C to supervisor - saves ALL sections including Section 4 and marks as submitted
    """
    user_id=session.get('id')
    
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    formA = db_session.query(FormA).filter_by(user_id=user_id).first()
    if formA:
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))
        
    formB = db_session.query(FormB).filter_by(user_id=user_id).first()
    if formB:
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))
    

    user = db_session.query(User).filter(User.user_id == user_id).first()
    supervisor=db_session.query(User).filter(User.user_id == user.supervisor_id).first()
    
    # Resolve the draft to submit. Never create a new row at submit time,
    # otherwise a stale/missing form_id can produce duplicate records.
    form = db_session.query(FormC).filter(FormC.user_id==user_id, FormC.form_id==form_id).first()
    form_exists = form is not None
    
    if not form_exists:
        # Fallback to the latest unsubmitted draft for this user.
        form = (
            db_session.query(FormC)
            .filter(FormC.user_id == user_id, FormC.submission_date.is_(None))
            .order_by(FormC.created_at.desc())
            .first()
        )
        if not form:
            flash("No draft Form C found to submit. Please open your draft and try again.", "warning")
            return redirect(url_for('student_continue_formc'))

    locked_response = redirect_if_student_form_locked(form, 'Form C')
    if locked_response:
        return locked_response
    
    if request.method=="POST":
        declaration_name=request.form.get('declaration_name')
        full_name=request.form.get('full_name')
        submission_date=get_local_time()
        
        # Validate Section 4 (Declaration) is complete
        if not (declaration_name and full_name):
            flash("Please complete all Section 4 (Declaration) fields before submitting.", "error")
            return redirect(url_for('student_continue_formc', form_id=form_id))
        
        # Helper function to convert checkbox values to boolean
        def to_bool(value):
            if isinstance(value, bool):
                return value
            if value is None:
                return False
            if isinstance(value, str):
                return value.lower() in ('yes', 'on', 'true', '1')
            return bool(value)
        
        try:
            # Process all form data (same as student_continue_formc)
            form.user_id = user_id
            form.applicant_name = request.form.get('applicant_name')
            form.student_number = request.form.get('student_number')
            form.institution = request.form.get('institution')
            form.department = request.form.get('department')
            form.degree = request.form.get('degree')
            form.project_title = request.form.get('project_title')
            form.mobile_number = request.form.get('mobile_number')
            form.email_address = user.email
            form.supervisor_name = supervisor.full_name if supervisor else ''
            form.supervisor_email = supervisor.email if supervisor else ''
            form.vulnerable = to_bool(request.form.get('vulnerable'))
            form.age_under_18_or_over_65 = to_bool(request.form.get('age_under_18_or_over_65'))
            form.uj_employees = to_bool(request.form.get('uj_employees'))
            form.non_vulnerable_context = to_bool(request.form.get('non_vulnerable_context'))
            form.non_english = to_bool(request.form.get('non_english'))
            form.own_students = to_bool(request.form.get('own_students'))
            form.poverty = to_bool(request.form.get('poverty'))
            form.no_education = to_bool(request.form.get('no_education'))
            form.vulnerable_other_description = to_bool(request.form.get('vulnerable_other_description'))
            form.vulnerable_comments = request.form.get('vulnerable_comments')
            form.consent_violation = to_bool(request.form.get('consent_violation'))
            form.discomfiture = to_bool(request.form.get('discomfiture'))
            form.deception = to_bool(request.form.get('deception'))
            form.sensitive_issues = to_bool(request.form.get('sensitive_issues'))
            form.prejudicial_info = to_bool(request.form.get('prejudicial_info'))
            form.intrusive = to_bool(request.form.get('intrusive'))
            form.illegal = to_bool(request.form.get('illegal'))
            form.direct_social_info = to_bool(request.form.get('direct_social_info'))
            form.identifiable_records = to_bool(request.form.get('identifiable_records'))
            form.psychology_tests = to_bool(request.form.get('psychology_tests'))
            form.researcher_risk = to_bool(request.form.get('researcher_risk'))
            form.activity_other_description = request.form.get('activity_other_description')
            form.activity_comments = request.form.get('activity_comments')
            form.incentives = to_bool(request.form.get('incentives'))
            form.participant_costs = to_bool(request.form.get('participant_costs'))
            form.researcher_interest = to_bool(request.form.get('researcher_interest'))
            form.conflict_of_interest = to_bool(request.form.get('conflict_of_interest'))
            form.uj_premises = to_bool(request.form.get('uj_premises'))
            form.uj_facilities = to_bool(request.form.get('uj_facilities'))
            form.uj_funding = to_bool(request.form.get('uj_funding'))
            form.consideration_comments = request.form.get('consideration_comments')
            form.risk_level = request.form.get('risk_level')
            form.risk_justification = request.form.get('risk_justification')
            form.risk_benefits = request.form.get('risk_benefits')
            form.risk_mitigation = request.form.get('risk_mitigation')
            form.summary_title = request.form.get('summary_title')
            form.executive_summary = request.form.get('executive_summary')
            form.research_questions = request.form.get('research_questions')
            form.research_purpose = request.form.get('research_purpose')
            form.secondary_data_info = request.form.get('secondary_data_info')
            form.exemption_reason = request.form.get('exemption_reason')
            
            # Section 4 - Mark as submitted
            form.declaration_name = declaration_name
            form.full_name = full_name
            form.submission_date = submission_date
            form.submitted = True
            form.rejected_or_accepted = False
            was_in_corrections = is_student_correction_state(form)
            form.status = 'Resubmitted' if was_in_corrections else 'Submitted'
            form.visible_to_student = False
            form.ethics_form_status = 'Resubmitted' if was_in_corrections else 'Submitted'
            form.form_supervisor_status = 'Resubmitted' if was_in_corrections else 'Submitted'
            reset_form_review_feedback(form)
            
            db_session.add(form)
            db_session.commit()

            # Send notifications
            try:
                message = 'You have successfully edited and submitted your form. Please wait while its under review.'
                send_email(app, mail, message, [user.email])
                messages = f'{form.applicant_name} has submitted a form that needs to be reviewed.'
                send_email(app, mail, messages, [form.supervisor_email])
            except Exception as e:
                app.logger.error(f"Failed to send email to {form.supervisor_email}: {e}")
            
            flash("Form successfully submitted to supervisor!", "success")
            return redirect(url_for('student_dashboard'))
            
        except Exception as e:
            db_session.rollback()
            app.logger.error(f"Error submitting Form C: {e}")
            flash("An error occurred while submitting the form. Please try again.", "error")
            return redirect(url_for('student_continue_formc', form_id=form_id))



@app.route('/form_c_answers', methods=['GET','POST'])
def form_c_answers():
    user_id=session.get('id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    form = db_session.query(FormC).filter_by(user_id=user_id).first()
    return render_template("form_c_answers.html",formc=form)
