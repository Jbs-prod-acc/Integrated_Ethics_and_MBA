from app_support import *

@app.route('/view_requirement_file')
@login_required
def view_requirement_file():
    # Retrieve all possible parameter names from both positional and query string
    # Since we removed positional from the route, url_for will pass them all as query params
    req_id = request.args.get('req_id')
    user_id = request.args.get('user_id')
    identifier = request.args.get('identifier')
    field = request.args.get('field')
    field_name = request.args.get('field_name')
    
    actual_id = req_id or user_id or identifier
    f_name = field or field_name
    
    if not actual_id or not f_name:
        return f"Missing parameters: req_id/user_id={actual_id}, field/field_name={f_name}", 400

    if f_name not in REQUIREMENT_FILE_FIELDS:
        abort(403)
        
    # Try finding by user_id first, then by primary key ID
    req = db_session.query(FormARequirements).filter(
        (FormARequirements.user_id == actual_id) | (FormARequirements.id == str(actual_id))
    ).first()
    
    if not req:
        return "Record not found", 404

    current_user = get_current_user()
    if not can_access_requirements(current_user, req):
        abort(403)
    
    # Use f_name from now on
    actual_field = f_name
    data = getattr(req, actual_field, None)
    
    # If data is a boolean (like ethics_evidence), it's not the file data. Try _path.
    if isinstance(data, bool) or data is None:
        if hasattr(req, f"{f_name}_path"):
            actual_field = f"{f_name}_path"
            data = getattr(req, actual_field)
            
    if not data:
        return "File content not found", 404

    # NEW: Handle memoryview (common when Column(Text) points to a bytea in DB)
    if isinstance(data, memoryview):
        try:
            # Try to decode as string - if it's a path, it will succeed
            data = bytes(data).decode('utf-8')
        except Exception:
            # It's likely actual binary data (BLOB)
            data = bytes(data)

    # Determine filename
    filename = getattr(req, f"{actual_field}_filename", None) or \
               getattr(req, f"{f_name}_filename", None) or \
               getattr(req, f_name.replace('_path', '') + "_filename", None) or \
               getattr(req, f_name.replace('_sheet', '') + "_filename", None) or \
               getattr(req, f_name.replace('_file', '') + "_filename", None)

    # NEW: Support for file paths instead of BLOBs
    if isinstance(data, str) and not data.startswith('\\x'):
        # Check if it looks like a path (e.g., "uploads/form/...")
        potential_path = _resolve_safe_static_file_path(data)
        if potential_path and potential_path.is_file():
            # Use mimetypes to be sure
            import mimetypes
            mtype, _ = mimetypes.guess_type(str(potential_path))
            return send_file(str(potential_path), mimetype=mtype or 'application/pdf', as_attachment=False, download_name=filename or potential_path.name)

    # Ensure data is bytes for processing if it was a BLOB
    if isinstance(data, str):
        if data.startswith('\\x'):
            data = bytes.fromhex(data[2:])
        else:
            data = data.encode('latin-1', errors='ignore')
    elif hasattr(data, 'read'): # Handle file-like objects
        data = data.read()
    
    # MAGIC NUMBER DETECTION for robustness
    is_pdf = data.startswith(b'%PDF-')
    is_zip = data.startswith(b'PK\x03\x04')
    
    mimetype = 'application/pdf' if is_pdf else 'application/octet-stream'
    
    if filename:
        filename = filename.strip()
        ext = filename.lower().split('.')[-1]
        if ext == 'pdf':
            mimetype = 'application/pdf'
        elif ext in ['doc', 'docx']:
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' if ext == 'docx' else 'application/msword'
        elif ext == 'zip':
            mimetype = 'application/zip'
        elif ext == 'png':
            mimetype = 'image/png'
        elif ext in ['jpg', 'jpeg']:
            mimetype = 'image/jpeg'
    else:
        # Fallback filename based on magic numbers
        if is_pdf:
            filename = f"{f_name}.pdf"
            mimetype = 'application/pdf'
        elif is_zip:
            filename = f"{f_name}.docx"
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        else:
            filename = f"{f_name}.dat"
            mimetype = 'application/octet-stream'

    return send_file(
        io.BytesIO(data),
        mimetype=mimetype,
        download_name=filename,
        as_attachment=False
    )


# --- Send Back for Corrections endpoint for FormB ---
@app.route('/send_back_for_corrections_b/<id>', methods=['POST'])
def send_back_for_corrections_b(id):
    try:
        form = db_session.query(FormB).filter_by(form_id=id).first()
        if not form:
            flash('Form B not found.', 'danger')
            return redirect(url_for('ethics_reviewer_committee_form_b'))
        if not has_all_required_reviews(form):
            flash('Form B can only be sent back after all assigned reviewers have submitted their reviews.', 'danger')
            return redirect(url_for('ethics_reviewer_committee_form_b'))
        feedback = (request.form.get('corrections_feedback') or '').strip()
        if not feedback:
            flash('A comment is required before sending Form B back for corrections.', 'danger')
            return redirect(url_for('ethics_reviewer_committee_form_b'))
        form.status = 'Submitted to Student for Corrections'
        form.review_form_status = feedback
        form.visible_to_student = True
        db_session.commit()
        flash('Form B sent back for corrections.', 'warning')
    except SQLAlchemyError as e:
        db_session.rollback()
        flash('Database error: {}'.format(str(e)), 'danger')
    return redirect(url_for('ethics_reviewer_committee_form_b'))

# --- Student resubmits corrected FormB ---
@app.route('/resubmit_formb/<id>', methods=['POST'])
def resubmit_formb(id):
    form_id = id
    user_id=session.get('id')
    formA = db_session.query(FormA).filter_by(user_id=user_id).first()
    if formA:
        print("[DEBUG] User has FormA, not permitted to submit FormB.")
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))
    formC = db_session.query(FormC).filter_by(user_id=user_id).first()
    if formC:
        print("[DEBUG] User has FormC, not permitted to submit FormB.")
        flash("You are not permitted to fill this form", "warning")
        return redirect(url_for("student_dashboard"))
    if not user_id:
        print("[DEBUG] No user_id in session, unauthorized.")
        return jsonify({'error': 'Unauthorized'}), 401
    user = db_session.query(User).filter(User.user_id == user_id).first()
    supervisor=db_session.query(User).filter(User.user_id == user.supervisor_id).first()
    print(f"[DEBUG] User: {user}")
    print(f"[DEBUG] Supervisor: {supervisor}")
    # Check if form exists in database - if yes UPDATE (mark as resubmitted), if no error
    form = db_session.query(FormB).filter(FormB.user_id==user_id, FormB.form_id==form_id).first()
    if not form:
        flash("Form not found for resubmission.", "danger")
        return redirect(url_for("student_dashboard"))

    if request.method == 'POST':
        if form.status not in ('Corrections Required', 'Submitted to Student for Corrections'):
            flash("Form B is not awaiting corrections.", "danger")
            return redirect(url_for("student_dashboard"))
        # Ensure reviewers are assigned before resubmission
        if assigned_reviewer_count(form) < 1:
            flash("You cannot resubmit Form B until at least one reviewer is assigned.", "danger")
            return redirect(url_for("student_dashboard"))
        # Mark as resubmitted, update timestamp, status, etc.
        form.ethics_supervisor_form_status = "Resubmitted"
        form.form_supervisor_status = "Resubmitted"
        form.submitted_at = get_local_time()
        form.status = "Resubmitted"
        form.visible_to_student = False
        reset_form_review_feedback(form)
        db_session.commit()
        flash("Form B resubmitted successfully.", "success")
        return redirect(url_for("student_dashboard"))


def inherit_previous_reviewers(new_form, model, user_id, order_column):
    """
    When a new version of a form is created, carry forward the latest assigned
    reviewers from the student's previous version so version history is kept
    without losing reviewer assignments.
    """
    previous_forms = (
        db_session.query(model)
        .filter(model.user_id == user_id, order_column.isnot(None))
        .order_by(order_column.desc().nullslast(), model.created_at.desc().nullslast())
        .all()
    )

    for previous_form in previous_forms:
        reviewer_name1 = getattr(previous_form, 'reviewer_name1', None)
        reviewer_name2 = getattr(previous_form, 'reviewer_name2', None)
        if reviewer_name1 or reviewer_name2:
            new_form.reviewer_name1 = reviewer_name1
            new_form.reviewer_name2 = reviewer_name2
            break


def get_reviewers_for_ethics_assignment(current_form, model, order_column):
    """
    On the ethics assignment screen, prefer reviewers already saved on the
    current version. If the current version is a fresh resubmission with no
    reviewers yet, fall back to the most recent previous version for the same
    student.
    """
    if not current_form:
        return []

    current_ids = [
        reviewer_id for reviewer_id in
        [getattr(current_form, 'reviewer_name1', None), getattr(current_form, 'reviewer_name2', None)]
        if reviewer_id
    ]
    if current_ids:
        return current_ids

    previous_forms = (
        db_session.query(model)
        .filter(
            model.user_id == current_form.user_id,
            model.form_id != current_form.form_id,
            order_column.isnot(None),
        )
        .order_by(order_column.desc().nullslast(), model.created_at.desc().nullslast())
        .all()
    )

    for previous_form in previous_forms:
        previous_ids = [
            reviewer_id for reviewer_id in
            [getattr(previous_form, 'reviewer_name1', None), getattr(previous_form, 'reviewer_name2', None)]
            if reviewer_id
        ]
        if previous_ids:
            return previous_ids

    return []

# --- Send Back for Corrections endpoint for FormC ---
@app.route('/send_back_for_corrections_c/<id>', methods=['POST'])
def send_back_for_corrections_c(id):
    try:
        form = db_session.query(FormC).filter_by(form_id=id).first()
        if not form:
            print('Form C not found.')
            flash('Form C not found.', 'danger')
            return redirect(url_for('ethics_reviewer_committee_form_c'))
        if not has_all_required_reviews(form):
            flash('Form C can only be sent back after all assigned reviewers have submitted their reviews.', 'danger')
            return redirect(url_for('ethics_reviewer_committee_form_c'))
        print(f"Form C status before corrections: {form.status}")
        feedback = (request.form.get('corrections_feedback') or '').strip()
        if not feedback:
            flash('A comment is required before sending Form C back for corrections.', 'danger')
            return redirect(url_for('ethics_reviewer_committee_form_c'))
        form.status = 'Submitted to Student for Corrections'
        form.review_form_status = feedback
        form.visible_to_student = True
        
        form.rejected_or_accepted = False
        db_session.commit()
        print('Form C sent back for corrections.')
        flash('Form C sent back for corrections.', 'warning')
    except SQLAlchemyError as e:
        db_session.rollback()
        print(f"âŒ Database error in send_back_for_corrections_c: {str(e)}")
        flash('Database error: {}'.format(str(e)), 'danger')
    return redirect(url_for('ethics_reviewer_committee_form_c'))

# --- Student resubmits corrected FormC ---
@app.route('/resubmit_formc/<id>', methods=['POST'])
def resubmit_formc(id):
    try:
        form = db_session.query(FormC).filter_by(form_id=id).first()
        if not form:
            print('Form C not found.')
            flash('Form C not found.', 'danger')
            return redirect(url_for('student_dashboard'))
        print(f"Form C status before resubmit: {form.status}")
        if form.status not in ('Corrections Required', 'Submitted to Student for Corrections'):
            print('Form C is not awaiting corrections.')
            flash('Form C is not awaiting corrections.', 'danger')
            return redirect(url_for('student_dashboard'))
        # Ensure reviewers are assigned before resubmission
        if assigned_reviewer_count(form) < 1:
            flash("You cannot resubmit Form C until at least one reviewer is assigned.", "danger")
            return redirect(url_for("student_dashboard"))
        # Update form fields from student input as needed
        form.submission_date = get_local_time()
        form.ethics_supervisor_form_status = "Resubmitted"
        form.form_supervisor_status = "Resubmitted"
        form.status = 'Resubmitted'
        form.visible_to_student = False
        reset_form_review_feedback(form)
        db_session.commit()
        print('Form C resubmitted to admin and supervisor.')
        flash('Form C resubmitted to admin and supervisor.', 'success')
    except SQLAlchemyError as e:
        db_session.rollback()
        print(f"âŒ Database error in resubmit_formc: {str(e)}")
        flash('Database error: {}'.format(str(e)), 'danger')
    return redirect(url_for('student_dashboard'))  

    

@app.route('/student_autosave_forma', methods=['POST'])
# Autosaves a logged-in student's Form A draft without submitting the form.
def student_autosave_forma():
    user_id = session.get('id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    form, error_response = _get_or_create_forma_draft(user_id, request.form)
    if error_response:
        return error_response

    _apply_forma_autosave_payload(form, request.form, section='all', include_declaration=False)

    try:
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500



# --- AUTOSAVE ENDPOINT FOR FORM B ---
def _get_or_create_formb_draft(user_id, form_data):
    form = db_session.query(FormB).filter_by(user_id=user_id).order_by(FormB.created_at.asc()).first()
    if form:
        return form, None

    user = db_session.query(User).filter(User.user_id == user_id).first()
    if not user:
        return None, (jsonify({'success': False, 'error': 'Unauthorized'}), 401)

    supervisor = db_session.query(User).filter(User.user_id == user.supervisor_id).first()

    form = FormB(
        user_id=user_id,
        applicant_name=form_data.get('applicant_name', ''),
        student_number=form_data.get('student_number', ''),
        institution=form_data.get('institution', 'University of Johannesburg'),
        department=form_data.get('department', ''),
        degree=form_data.get('degree', ''),
        study_title=form_data.get('study_title', ''),
        mobile=form_data.get('mobile', ''),
        email=(user.email or ''),
        supervisor=(supervisor.full_name if supervisor else ''),
        supervisor_email=(supervisor.email if supervisor else ''),
        submitted=False,
    )
    db_session.add(form)
    return form, None

# Autosaves a logged-in student's Form B draft without submitting the form.
@app.route('/student_autosave_formb', methods=['POST'])
def student_autosave_formb():
    user_id = session.get('id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    form, error_response = _get_or_create_formb_draft(user_id, request.form)
    if error_response:
        return error_response

    def str_to_bool(val):
        if isinstance(val, bool):
            return val
        if val is None:
            return None
        if isinstance(val, str):
            if val.lower() in ['yes', 'true', '1', 'on', 'checked']:
                return True
            if val.lower() in ['no', 'false', '0', 'off', '']:
                return False
        return val

    boolean_fields = [
        'data_public',
        'personal_info',
        'private_permission',
        'shortcomings_reported',
        'methodology_alignment'
    ]
    declaration_fields = {'declaration_name', 'full_name', 'declaration_date'}

    data = request.form.to_dict()
    for key, value in data.items():
        if key not in declaration_fields and hasattr(form, key):
            if key in boolean_fields:
                setattr(form, key, str_to_bool(value))
            elif key in ['supervisor_date', 'supervisor_signature']:
                # Set to None if empty string, to avoid invalid timestamp errors
                setattr(form, key, value if value else None)
            else:
                setattr(form, key, value)
    try:
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        import traceback
        db_session.rollback()
        print('\n' + '='*60)
        print('âŒ Exception in student_autosave_formb:', str(e))
        print('--- TRACEBACK BELOW ---')
        traceback.print_exc()
        print('='*60 + '\n')
        return jsonify({'success': False, 'error': str(e)}), 500

# --- AUTOSAVE ENDPOINT FOR FORM C ---
def _get_or_create_formc_draft(user_id, form_data):
    form = db_session.query(FormC).filter_by(user_id=user_id).order_by(FormC.created_at.asc()).first()
    if form:
        return form, None

    user = db_session.query(User).filter(User.user_id == user_id).first()
    if not user:
        return None, (jsonify({'success': False, 'error': 'Unauthorized'}), 401)

    supervisor = db_session.query(User).filter(User.user_id == user.supervisor_id).first()

    form = FormC(
        user_id=user_id,
        applicant_name=form_data.get('applicant_name', ''),
        student_number=form_data.get('student_number', ''),
        institution=form_data.get('institution', 'University of Johannesburg'),
        department=form_data.get('department', ''),
        degree=form_data.get('degree', ''),
        project_title=form_data.get('project_title', ''),
        mobile_number=form_data.get('mobile_number', ''),
        email_address=(user.email or ''),
        supervisor_name=(supervisor.full_name if supervisor else ''),
        supervisor_email=(supervisor.email if supervisor else ''),
        submitted=False,
    )
    db_session.add(form)
    return form, None


@app.route('/student_autosave_formc', methods=['POST'])
# Autosaves a logged-in student's Form C draft without submitting the form.
def student_autosave_formc():
    user_id = session.get('id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    form, error_response = _get_or_create_formc_draft(user_id, request.form)
    if error_response:
        return error_response

    def str_to_bool(val):
        if isinstance(val, bool):
            return val
        if val is None:
            return None
        if isinstance(val, str):
            if val.lower() in ['yes', 'true', '1', 'on', 'checked']:
                return True
            if val.lower() in ['no', 'false', '0', 'off', '']:
                return False
        return val

    boolean_fields = [
        'vulnerable',
        'age_under_18_or_over_65',
        'uj_employees',
        'non_vulnerable_context',
        'non_english',
        'own_students',
        'poverty',
        'no_education',
        'consent_violation',
        'discomfiture',
        'deception',
        'sensitive_issues',
        'prejudicial_info',
        'intrusive',
        'illegal',
        'direct_social_info',
        'identifiable_records',
        'psychology_tests',
        'researcher_risk',
        'incentives',
        'participant_costs',
        'researcher_interest',
        'conflict_of_interest',
        'uj_premises',
        'uj_facilities',
        'uj_funding'
    ]
    declaration_fields = {'declaration_name', 'full_name', 'submission_date'}

    data = request.form.to_dict()

    if 'uj_employee' in data and 'uj_employees' not in data:
        data['uj_employees'] = data['uj_employee']
    if 'own_student' in data and 'own_students' not in data:
        data['own_students'] = data['own_student']
    if 'non_education' in data and 'no_education' not in data:
        data['no_education'] = data['non_education']
    if 'prejuditial_info' in data and 'prejudicial_info' not in data:
        data['prejudicial_info'] = data['prejuditial_info']
    if 'reseacher_risk' in data and 'researcher_risk' not in data:
        data['researcher_risk'] = data['reseacher_risk']

    for key, value in data.items():
        if key not in declaration_fields and hasattr(form, key):
            if key in boolean_fields:
                setattr(form, key, str_to_bool(value))
            else:
                setattr(form, key, value)
    try:
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# --- AUTOSAVE ENDPOINTS FOR FORM A SECTIONS ---

def _get_or_create_forma_draft(user_id, form_data):
    form_data = form_data or {}
    form_id = form_data.get('forma_id') or session.get('active_forma_id')

    # Prefer explicit draft id from the client when available.
    if form_id:
        form = db_session.query(FormA).filter_by(user_id=user_id, form_id=form_id).first()
        if form and not (form.submitted_at is None and has_reviewer_feedback(form)):
            session['active_forma_id'] = form.form_id
            return form, None

    # Otherwise, reuse the latest unsubmitted draft for this user.
    unsubmitted_drafts = (
        db_session.query(FormA)
        .filter(FormA.user_id == user_id, FormA.submitted_at.is_(None))
        .order_by(FormA.created_at.desc().nullslast())
        .all()
    )
    for form in unsubmitted_drafts:
        if has_reviewer_feedback(form):
            continue
        session['active_forma_id'] = form.form_id
        return form, None

    form_requirements = db_session.query(FormARequirements).filter_by(user_id=user_id).first()

    user = db_session.query(User).filter(User.user_id == user_id).first()
    if not user:
        return None, (jsonify({'success': False, 'error': 'User not found'}), 404)

    supervisor = db_session.query(User).filter(User.user_id == user.supervisor_id).first()

    form = FormA(
        user_id=user_id,
        attachment_id=(form_requirements.id if form_requirements else (form_data.get('attachment_id') or 'AUTOSAVE_PENDING')),
        applicant_name=form_data.get('applicant_name', ''),
        student_number=form_data.get('student_number', ''),
        institution=form_data.get('institution', 'University of Johannesburg'),
        department=form_data.get('department', ''),
        degree=form_data.get('degree', ''),
        study_title=form_data.get('study_title', ''),
        mobile=form_data.get('mobile', ''),
        email=(user.email or ''),
        supervisor=(supervisor.full_name if supervisor else ''),
        supervisor_email=(supervisor.email if supervisor else ''),
    )
    db_session.add(form)
    db_session.flush()
    session['active_forma_id'] = form.form_id
    return form, None

def _get_latest_forma_for_user(user_id):
    if not user_id:
        return None

    active_form_id = session.get('active_forma_id')
    if active_form_id:
        active_form = db_session.query(FormA).filter_by(user_id=user_id, form_id=active_form_id).first()
        if active_form and not (active_form.submitted_at is None and has_reviewer_feedback(active_form)):
            return active_form

    latest_clean_draft = (
        db_session.query(FormA)
        .filter(FormA.user_id == user_id, FormA.submitted_at.is_(None))
        .order_by(FormA.created_at.desc().nullslast())
        .all()
    )
    for form in latest_clean_draft:
        if not has_reviewer_feedback(form):
            return form

    return (
        db_session.query(FormA)
        .filter(FormA.user_id == user_id)
        .order_by(FormA.submitted_at.desc().nullslast(), FormA.created_at.desc().nullslast())
        .first()
    )

def _autosave_str_to_bool(val):
    if isinstance(val, bool):
        return val
    if val is None:
        return None
    if isinstance(val, str):
        if val.lower() in ['yes', 'true', '1', 'on', 'checked']:
            return True
        if val.lower() in ['no', 'false', '0', 'off', '']:
            return False
    return val

def _build_autosave_data(form_payload):
    data = {}
    for key in form_payload.keys():
        if key in {'csrf_token', 'forma_id'}:
            continue
        values = form_payload.getlist(key)
        normalized_key = key[:-2] if key.endswith('[]') else key
        if key in ['quantitative[]', 'qualitative[]', 'mixed_methods[]']:
            data[normalized_key] = True if values else False
        elif len(values) > 1:
            data[normalized_key] = ','.join(values)
        else:
            data[normalized_key] = values[0] if values else ''
    return data


def _apply_forma_autosave_payload(form, form_payload, section='all', include_declaration=False):
    data = _build_autosave_data(form_payload)

    if 'secondary_data' in data and 'uses_secondary_data' not in data:
        data['uses_secondary_data'] = data['secondary_data']
    if 'privatePermission' in data and 'private_permission' not in data:
        data['private_permission'] = data['privatePermission']

    if 'questionnaire_permission' in data:
        questionnaire_permission = (data.get('questionnaire_permission') or '').strip()
        if questionnaire_permission == 'Yes':
            data['permission_obtained'] = 'Yes'
            data['open_source'] = 'No'
        elif questionnaire_permission == 'Open Source':
            data['permission_obtained'] = 'No'
            data['open_source'] = 'Yes'
        else:
            data['permission_obtained'] = None
            data['open_source'] = None

    sec2_bool_fields = [
        'survey', 'focus_groups', 'observations', 'interviews', 'documents',
        'vulnerable_communities', 'age_range', 'uj_employees', 'vulnerable', 'non_english',
        'own_students', 'poverty', 'no_education', 'disclosure', 'discomfiture', 'deception',
        'sensitive', 'prejudice', 'intrusive_techniques', 'illegal_activities', 'personal',
        'available_records', 'inventories', 'risk_activities', 'incentives', 'financial_costs',
        'reward', 'conflict', 'uj_premises', 'uj_facilities', 'uj_funding'
    ]

    sec4_bool_fields = [
        'quantitative', 'qualitative', 'mixed_methods', 'conflict_interest',
        'intervention', 'translator', 'uses_secondary_data'
    ]

    sec5_bool_fields = [f'q6_9{key}' for key in ['a','b','c','d','e','f','g','h','i','j','k','l','m','n','o','p','q','r','s']]

    all_bool_fields = set(sec2_bool_fields + sec4_bool_fields + sec5_bool_fields + ['interviews_one', 'documents_one'])
    for key in list(data.keys()):
        if key in all_bool_fields:
            data[key] = _autosave_str_to_bool(data[key])

    if section in ['all', 'sec1']:
        for key in ['applicant_name', 'student_number', 'institution', 'department', 'degree', 'study_title', 'mobile', 'email', 'supervisor', 'supervisor_email']:
            if key in data and hasattr(form, key):
                setattr(form, key, data.get(key, ''))

    if section in ['all', 'sec2']:
        for key in sec2_bool_fields:
            if section == 'all':
                setattr(form, key, _autosave_str_to_bool(data[key]) if key in data else False)
            else:
                setattr(form, key, _autosave_str_to_bool(data[key]) if key in data else False)

        for key in ['assessment_other_specify', 'vulnerable_other_specify', 'activity_specify', 'vulnerable_comments_1', 'vulnerable_comments_2', 'vulnerable_comments_3', 'risk_rating', 'risk_justification', 'benefits_description', 'risk_mitigation', 'apply_comments', 'other_sec2']:
            if key in data and hasattr(form, key):
                setattr(form, key, data.get(key, ''))

        if hasattr(form, 'interviews_one'):
            form.interviews_one = _autosave_str_to_bool(data.get('interviews')) if 'interviews' in data else False
        if hasattr(form, 'documents_one'):
            form.documents_one = _autosave_str_to_bool(data.get('documents')) if 'documents' in data else False

    if section in ['all', 'sec3']:
        for key in ['title_provision', 'abstract', 'questions', 'purpose_objectives', 'grant_permission', 'researcher_affiliation', 'affiliation_details', 'collective_involvement', 'collective_details', 'is_funded', 'indemnity_arrangements', 'other_committee']:
            if key in data and hasattr(form, key):
                setattr(form, key, data.get(key, ''))

        form.org_name = ','.join(form_payload.getlist('org_name[]'))
        form.org_contact = ','.join(form_payload.getlist('org_contact[]'))
        form.org_role = ','.join(form_payload.getlist('org_role[]'))
        form.org_permission = ','.join(form_payload.getlist('org_permission[]'))
        form.fund_org = ','.join(form_payload.getlist('fund_org[]'))
        form.fund_contact = ','.join(form_payload.getlist('fund_contact[]'))
        form.fund_role = ','.join(form_payload.getlist('fund_role[]'))
        form.fund_amount = ','.join(form_payload.getlist('fund_amount[]'))

    if section in ['all', 'sec4']:
        for key in sec4_bool_fields:
            if section == 'all':
                setattr(form, key, _autosave_str_to_bool(data[key]) if key in data else False)
            else:
                setattr(form, key, _autosave_str_to_bool(data[key]) if key in data else False)

        for paradigm_field in ['quantitative', 'qualitative', 'mixed_methods']:
            if section == 'all' and paradigm_field not in data:
                setattr(form, paradigm_field, False)

        for key in ['paradigm_explanation', 'design', 'participants_description', 'duration_timing', 'contact_details_method', 'conflict_explanation', 'questionnaire_type', 'permission_obtained', 'open_source', 'instrument_attachment_reason', 'interview_type', 'interview_recording', 'focus_recording', 'observation_details', 'documents_details', 'other_details', 'data_collection_procedure', 'data_collectors', 'intervention_details', 'sensitive_data', 'translator_procedure', 'data_nature', 'data_origin', 'access_conditions', 'personal_info', 'personal_info_comment', 'data_anonymized', 'anonymization_comment', 'permission_details', 'public_data_description', 'shortcomings_reported', 'limitations_reporting', 'methodology_alignment', 'data_acknowledgment', 'secondary_data_type', 'private_permission']:
            if key in data and hasattr(form, key):
                setattr(form, key, data.get(key, ''))

        form.population = ','.join(form_payload.getlist('population[]'))
        form.sampling_method = ','.join(form_payload.getlist('sampling_method[]'))
        form.sampling_size = ','.join(form_payload.getlist('sample_size[]'))
        form.inclusion_criteria = ','.join(form_payload.getlist('inclusion_criteria[]'))
        form.data_methods = ','.join(form_payload.getlist('data_methods[]'))

        selected_methods = [method.strip() for method in form.data_methods.split(',') if method.strip()]
        form.use_focus_groups = 'focus' in selected_methods

        if 'data_type' in data:
            form.secondary_data_type = data.get('data_type', '')

        if 'private_permission' in data:
            private_permission_value = data.get('private_permission')
            if isinstance(private_permission_value, str) and private_permission_value.lower() in ['yes', 'no']:
                form.private_permission = private_permission_value.capitalize()
            else:
                form.private_permission = 'Yes' if _autosave_str_to_bool(private_permission_value) else 'No'

        if hasattr(form, 'uses_secondary_data') and not form.uses_secondary_data:
            form.secondary_data_type = ''
            form.private_permission = ''

    if section in ['all', 'sec5']:
        for key in ['informed_consent', 'study_benefits', 'participant_risks', 'adverse_steps', 'community_participation', 'community_effects', 'results_feedback', 'products_access', 'publication_plans', 'participant_comp', 'participant_costs', 'ethics_reporting']:
            if key in data and hasattr(form, key):
                setattr(form, key, data.get(key, ''))

        form.data_storage = ','.join(form_payload.getlist('data_storage[]'))
        form.privacy = ','.join(form_payload.getlist('privacy[]'))

        for key in sec5_bool_fields:
            if section == 'all':
                setattr(form, key, _autosave_str_to_bool(data[key]) if key in data else False)
            else:
                setattr(form, key, _autosave_str_to_bool(data[key]) if key in data else False)

    if section in ['all', 'sec6'] and include_declaration:
        if 'declaration_name' in data:
            form.declaration_name = data.get('declaration_name', '')
        if 'applicant_signature' in data:
            form.applicant_signature = data.get('applicant_signature', '')

        date_str = data.get('declaration_date', '')
        if date_str:
            try:
                form.declaration_date = datetime.strptime(date_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                pass

@app.route('/form_a_sec1_autosave', methods=['POST'])
def form_a_sec1_autosave():
    """Autosave for Form A Section 1 - Researcher's Details"""
    user_id = session.get('id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    form, error_response = _get_or_create_forma_draft(user_id, request.form)
    if error_response:
        return error_response

    _apply_forma_autosave_payload(form, request.form, section='sec1', include_declaration=False)
    
    try:
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        print(f"âŒ Error in form_a_sec1_autosave: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/form_a_sec2_autosave', methods=['POST'])
def form_a_sec2_autosave():
    """Autosave for Form A Section 2 - Ethical Considerations"""
    user_id = session.get('id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    form, error_response = _get_or_create_forma_draft(user_id, request.form)
    if error_response:
        return error_response

    _apply_forma_autosave_payload(form, request.form, section='sec2', include_declaration=False)
    
    try:
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        print(f"âŒ Error in form_a_sec2_autosave: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/form_a_sec3_autosave', methods=['POST'])
def form_a_sec3_autosave():
    """Autosave for Form A Section 3 - Project Information & Affiliations"""
    user_id = session.get('id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    form, error_response = _get_or_create_forma_draft(user_id, request.form)
    if error_response:
        return error_response

    _apply_forma_autosave_payload(form, request.form, section='sec3', include_declaration=False)
    
    try:
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        print(f"âŒ Error in form_a_sec3_autosave: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/form_a_sec4_autosave', methods=['POST'])
def form_a_sec4_autosave():
    """Autosave for Form A Section 4 - Methodology"""
    user_id = session.get('id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    form, error_response = _get_or_create_forma_draft(user_id, request.form)
    if error_response:
        return error_response

    _apply_forma_autosave_payload(form, request.form, section='sec4', include_declaration=False)
    
    try:
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        print(f"âŒ Error in form_a_sec4_autosave: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/form_a_sec5_autosave', methods=['POST'])
def form_a_sec5_autosave():
    """Autosave for Form A Section 5 - Ethical Considerations"""
    user_id = session.get('id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    form, error_response = _get_or_create_forma_draft(user_id, request.form)
    if error_response:
        return error_response

    _apply_forma_autosave_payload(form, request.form, section='sec5', include_declaration=False)
    
    try:
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        print(f"âŒ Error in form_a_sec5_autosave: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/form_a_sec6_autosave', methods=['POST'])
@app.route('/form_a_sec7_autosave', methods=['POST'])
def form_a_sec6_autosave():
    """Autosave for Form A Section 6/7 - Declaration"""
    user_id = session.get('id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    form, error_response = _get_or_create_forma_draft(user_id, request.form)
    if error_response:
        return error_response

    _apply_forma_autosave_payload(form, request.form, section='sec6', include_declaration=True)
    
    try:
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        print(f"âŒ Error in form_a_sec6_autosave: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

    
@app.route('/view_form_file/<form_type>/<form_id>/<field_name>')
@app.route('/view_form_file/<form_type>/<form_id>')
@login_required
def view_form_file(form_type, form_id, field_name=None):
    f_name = field_name or request.args.get('field_name') or request.args.get('field')
    
    if not f_name:
        return "Missing field_name", 400

    if f_name not in FORM_FILE_FIELDS.get(str(form_type).upper(), set()):
        abort(403)

    model_map = {
        'A': FormA,
        'FormA': FormA,
        'B': FormB,
        'FormB': FormB,
        'C': FormC,
        'FormC': FormC
    }
    model = model_map.get(form_type)
    if not model:
        return "Invalid model", 400
        
    form = db_session.query(model).filter_by(form_id=form_id).first()
    if not form:
        return "Form not found", 404

    current_user = get_current_user()
    if not can_access_form(current_user, form):
        abort(403)
        
    data = getattr(form, f_name, None)
    if not data:
        return "File not found", 404

    # NEW: Handle memoryview
    if isinstance(data, memoryview):
        try:
            data = bytes(data).decode('utf-8')
        except Exception:
            data = bytes(data)

    # Better filename detection
    filename = getattr(form, f"{f_name}_filename", None) or \
               getattr(form, f_name.replace('_path', '') + "_filename", None) or \
               getattr(form, f_name.replace('_file', '') + "_filename", None)
               
    # Ensure data is bytes for processing
    if isinstance(data, str):
        if data.startswith('\\x'):
            data = bytes.fromhex(data[2:])
        elif len(data) < 500:
            # It might be a legacy file path if it's short
            clean_path = data.replace('\\', '/')
            if clean_path.startswith('static/'):
                clean_path = clean_path.replace('static/', '', 1)
            file_path = _resolve_safe_static_file_path(clean_path)
            if file_path and file_path.exists():
                # Determine mimetype from filename or fallback
                mtype, _ = mimetypes.guess_type(str(file_path))
                return send_file(str(file_path), mimetype=mtype or 'application/pdf', as_attachment=False)
            # If path doesn't exist, try encoding as bytes
            data = data.encode('latin-1')
        else:
            data = data.encode('latin-1')

    # MAGIC NUMBER DETECTION for robustness
    is_pdf = data.startswith(b'%PDF-')
    is_zip = data.startswith(b'PK\x03\x04')
    
    mimetype = 'application/pdf' if is_pdf else 'application/octet-stream'
    
    if filename:
        filename = filename.strip()
        ext = filename.lower().split('.')[-1]
        if ext == 'pdf':
            mimetype = 'application/pdf'
        elif ext in ['doc', 'docx']:
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' if ext == 'docx' else 'application/msword'
        elif ext == 'zip':
            mimetype = 'application/zip'
        elif ext == 'png':
            mimetype = 'image/png'
        elif ext in ['jpg', 'jpeg']:
            mimetype = 'image/jpeg'
    else:
        # Fallback filename based on magic numbers
        if is_pdf:
            filename = f"{f_name}.pdf"
            mimetype = 'application/pdf'
        elif is_zip:
            filename = f"{f_name}.docx"
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        else:
            filename = f"{f_name}.dat"
            mimetype = 'application/octet-stream'

    return send_file(
        io.BytesIO(data),
        mimetype=mimetype,
        download_name=filename,
        as_attachment=False
    )

db = SQLAlchemy(app)
migrate = Migrate(app, db)

web_url='https://jbs-ethics.onrender.com'

##import dummy_data

##dummy_data


# Health check endpoint for Render
@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200

    
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

def get_upload_folder():
    """
    Get the upload folder path - uses persistent disk on production, local folder for development
    """
    # Check if we're on Render.com production with persistent disk
    persistent_path = os.getenv('UPLOAD_PATH')
    if persistent_path and os.path.exists(os.path.dirname(persistent_path)):
        upload_folder = os.path.join(persistent_path, 'form')
        os.makedirs(upload_folder, exist_ok=True)
        return upload_folder
    
    # Fallback to local static folder for development
    local_path = os.path.join('static', 'uploads', 'form')
    os.makedirs(local_path, exist_ok=True)
    return local_path

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def read_file_blob(file_obj_or_key):
    """Read file content and return (binary_data, filename)."""
    if isinstance(file_obj_or_key, str):
        file = request.files.get(file_obj_or_key)
    else:
        file = file_obj_or_key
        
    if not file or file.filename == '':
        return None, None
    if allowed_file(file.filename):
        return file.read(), secure_filename(file.filename)
    return None, None


# DEBUG ENDPOINT REMOVED FOR PRODUCTION SECURITY

# --- Send Back for Corrections endpoint for FormA ---
from sqlalchemy.exc import SQLAlchemyError


# --- Send Back for Corrections endpoint for FormA ---
@app.route('/send_back_for_corrections/<id>', methods=['POST'], endpoint='send_back_for_corrections')
@app.route('/send_back_for_corrections_a/<id>', methods=['POST'])
def send_back_for_corrections_a(id):
    try:
        form = db_session.query(FormA).filter_by(form_id=id).first()
        if not form:
            flash('Form not found.', 'danger')
            return redirect(url_for('ethics_reviewer_committee_form_a'))
        if not has_all_required_reviews(form):
            flash('Form A can only be sent back after all assigned reviewers have submitted their reviews.', 'danger')
            return redirect(url_for('ethics_reviewer_committee_form_a'))
        # Mark the form as needing corrections and add feedback
        feedback = (request.form.get('corrections_feedback') or '').strip()
        if not feedback:
            flash('A comment is required before sending Form A back for corrections.', 'danger')
            return redirect(url_for('ethics_reviewer_committee_form_a'))
        form.status = 'Submitted to Student for Corrections'
        form.review_form_status = feedback
        form.visible_to_student = True  # Ensure student sees it in dashboard
        db_session.commit()
        flash('Form sent back for corrections.', 'warning')
    except SQLAlchemyError as e:
        db_session.rollback()
        flash('Database error: {}'.format(str(e)), 'danger')
    return redirect(url_for('ethics_reviewer_committee_form_a'))

# --- Student resubmits corrected FormA ---
@app.route('/resubmit_forma/<id>', methods=['POST'])
def resubmit_forma(id):
    try:
        form = db_session.query(FormA).filter_by(form_id=id).first()
        if not form:
            flash('Form not found.', 'danger')
            return redirect(url_for('student_dashboard'))
        # Only allow resubmission if corrections were required
        if form.status not in ('Corrections Required', 'Submitted to Student for Corrections'):
            flash('Form is not awaiting corrections.', 'danger')
            return redirect(url_for('student_dashboard'))
        # Ensure reviewers are assigned before resubmission
        if assigned_reviewer_count(form) < 1:
            flash('You cannot resubmit Form A until at least one reviewer is assigned.', 'danger')
            return redirect(url_for('student_dashboard'))
        form.status = 'Resubmitted'
        form.ethics_supervisor_form_status = 'Resubmitted'
        form.form_supervisor_status = 'Resubmitted'
        form.submitted_at = get_local_time()
        form.visible_to_student = False
        reset_form_review_feedback(form)
        db_session.commit()
        flash('Form resubmitted to admin and supervisor.', 'success')
    except SQLAlchemyError as e:
        db_session.rollback()
        flash('Database error: {}'.format(str(e)), 'danger')
    return redirect(url_for('student_dashboard'))
# Use proper logging and monitoring tools instead


# Adding an exception handler

from sqlalchemy.exc import SQLAlchemyError, OperationalError
import time

@app.errorhandler(SQLAlchemyError)
def handle_db_errors(e):
    # Safely rollback the session, handling cases where session is in a bad state
    try:
        db_session.rollback()
    except Exception as rollback_error:
        # If rollback fails, try to remove the session entirely
        try:
            db_session.remove()
        except Exception:
            pass
    
    # Handle SSL connection errors specifically
    if isinstance(e, OperationalError) and "SSL error" in str(e):
        print(f"Database SSL connection error: {e}")
        # For SSL errors, we could try to reconnect or show a user-friendly message
        return render_template('error.html', 
                             error_message="Database connection temporarily unavailable. Please try again in a moment."), 503
    
    raise e



