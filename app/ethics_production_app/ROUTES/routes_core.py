from app_support import *

@app.route('/api')
def index():
    response={
         "message": "Welocme",
    }
    return jsonify(response), 200

def check_user_has_submitted_forms(user_id):
    """
    Check if user has submitted any form (FormA, FormB, or FormC)
    Returns True if user has submitted any form, False otherwise
    """
    try:
        # Check FormA submissions
        form_a_exists = db_session.query(FormA).filter_by(user_id=user_id).first()
        if form_a_exists:
            return True
            
        # Check FormB submissions
        form_b_exists = db_session.query(FormB).options(
            defer(FormB.permission_letter),
            defer(FormB.prior_clearance),
            defer(FormB.ethics_evidence),
            defer(FormB.proposal_path),
            defer(FormB.pending_note),
            defer(FormB.private_permission_file)
        ).filter_by(user_id=user_id).first()
        if form_b_exists:
            return True
            
        # Check FormC submissions
        form_c_exists = db_session.query(FormC).filter_by(user_id=user_id).first()
        if form_c_exists:
            return True
            
        return False
    except Exception as e:
        print(f"Error checking user form submissions: {e}")
        return False


@app.route("/checks_if_student_submitted_forms",methods=['POST','GET'] )
def checks_if_student_submitted_forms():
    user_id=session.get('id')
    has_submitted = check_user_has_submitted_forms(user_id)
    if has_submitted:
        return redirect(url_for('student_dashboard'))
        




@app.route('/student_ethics_pack_to_dashboards', methods=['GET','POST'])
def student_ethics_pack_to_dashboards():
    user_id=session.get('id')
    
    # Check if user has already submitted any form
    if check_user_has_submitted_forms(user_id):
        return redirect(url_for('student_dashboard'))
    
    if request.method == 'GET':
        return redirect(url_for('ethics_pack'))

    selected_form = (request.form.get('selected_form') or '').strip().upper()

    if selected_form == 'A':

        return render_template('form-a-upload.html')

    elif selected_form == 'B':

        return render_template('form-b-upload.html')

    elif selected_form == 'C':

        return render_template('form-c-upload.html')

    return redirect(url_for('ethics_pack'))
    


    
@app.route('/student-dashboard', methods=['GET'])
def student_dashboard():
    try:
        user_id = session.get('id')

        if not user_id:
            return redirect(url_for('login_page'))

        user = db_session.query(User).filter_by(user_id=user_id).first()

        formA = _find_all_forms_for_user(FormA, user_id)
        formB = _find_all_forms_for_user(
            FormB,
            user_id,
            options=[
                defer(FormB.permission_letter),
                defer(FormB.prior_clearance),
                defer(FormB.ethics_evidence),
                defer(FormB.proposal_path),
                defer(FormB.pending_note),
                defer(FormB.private_permission_file),
            ],
        )
        formC = _find_all_forms_for_user(FormC, user_id)
        formD = db_session.query(FormD).filter_by(user_id=user_id).first()

        full_name = user.full_name if user else "Unknown User"

        # Check if student has FormARequirements and if files still exist
        form_requirements = db_session.query(FormARequirements).filter_by(user_id=user_id).first()
        files_missing = False
        missing_files_info = {}
        
        if not form_requirements:
            # Check if uploaded files still exist on the filesystem
            return redirect(url_for('ethics_pack'))
            
            
        return render_template(
            'dashboard.html',
            full_name=full_name,
            formA=formA,
            formB=formB,
            formC=formC,
            formD=formD,
            current_form_a_id=formA[0].form_id if formA else None,
            current_form_b_id=formB[0].form_id if formB else None,
            current_form_c_id=formC[0].form_id if formC else None,
            form_requirements=form_requirements,
            files_missing=files_missing,
            missing_files_info=missing_files_info
        )
    except Exception as e:
        # log error safely
        app.logger.error(f"Error loading student dashboard: {e}")
        return "An unexpected error occurred. Please try again later.", 500


@app.route('/quiz', methods=['GET'])
def quiz():
    return render_template('quiz.html')


@app.route('/logout', methods=['GET'])
def logout():
    clear_auth_session()
    return redirect(url_for('login_page'))

# Auto-logout after 45 minutes of inactivity
@app.before_request
def auto_logout():
    # Only check for logged-in students
    if 'id' in session:
        user_role = session.get('role')
        # Only apply auto-logout to students
        if user_role and str(user_role).upper() == 'STUDENT':
            now = datetime.utcnow()
            last_active = session.get('last_active')
            # If never set, set now
            if not last_active:
                session['last_active'] = now.isoformat()
            else:
                try:
                    last_active_dt = datetime.fromisoformat(last_active)
                except Exception:
                    # fallback if format is wrong
                    last_active_dt = now
                # If inactive for more than 45 minutes
                if now - last_active_dt > timedelta(minutes=60):
                    session.clear()
                    return redirect(url_for('login_page'))
            # Always update last_active if not logging out
            session['last_active'] = now.isoformat()


@app.before_request
def start_request_activity_timer():
    g.request_started_at = time.time()


@app.after_request
def capture_logged_in_user_activity(response):
    if request.endpoint == 'static' or not session.get('id'):
        return response

    if getattr(g, 'activity_already_logged', False):
        return response

    request_started_at = getattr(g, 'request_started_at', None)
    duration_seconds = None
    if request_started_at is not None:
        duration_seconds = max(0, int(round(time.time() - request_started_at)))

    action = 'request_error' if response.status_code >= 400 else 'page_visit'
    details = {
        'method': request.method,
        'path': request.path,
        'endpoint': request.endpoint,
        'status_code': response.status_code,
        'query_params': request.args.to_dict(flat=True),
    }

    try:
        create_user_activity_entry(
            user_id=session.get('id'),
            action=action,
            page=request.path,
            details=details,
            duration_seconds=duration_seconds
        )
        g.activity_already_logged = True
    except Exception:
        try:
            db_session.rollback()
        except Exception:
            pass

    return response


@app.teardown_request
def capture_logged_in_user_exceptions(exception=None):
    if not exception or request.endpoint == 'static' or not session.get('id'):
        return None

    details = {
        'method': request.method,
        'path': request.path,
        'endpoint': request.endpoint,
        'error_type': type(exception).__name__,
        'error_message': str(exception),
    }

    try:
        create_user_activity_entry(
            user_id=session.get('id'),
            action='request_exception',
            page=request.path,
            details=details,
            duration_seconds=None
        )
    except Exception:
        try:
            db_session.rollback()
        except Exception:
            pass
    return None


###
###
### this is the function to focus on when intergrating MBA and Ethics
###
@app.route('/')
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'GET' and 'id' in session:
        clear_auth_session()

    if request.method == 'POST':
        email = request.form.get('email')
        user_password = request.form.get('password')
        email = request.form.get('email')
        user_password = request.form.get('password')
        user = db_session.query(User).filter_by(email=email).first()
        
        
        if user:
            if user.verify_password(user_password):
                # Block unauthenticated user from logging in
                # Check if authenticate_student is falsy (False, "False", "false", None, empty string, etc.)
                if not user.authenticate_student or str(user.authenticate_student).lower() in ['false', '0', 'none']:
                        clear_auth_session()
                        flash("You are authenticated. Please wait for admin approval.", "danger")
                        return render_template('login.html', messages=["You are authenticated. Please wait for admin approval."])
                
                clear_auth_session()
                session['loggedin'] = True
                session['id'] = user.user_id
                session['name'] = user.full_name
                # Set last_active on successful login
                session['last_active'] = datetime.utcnow().isoformat()
                # Store user role in session
                session['role'] = user.role.value or 'student'

                # Persist a login audit record for every successful sign-in.
                db_session.add(UserActivityLog(
                    user_id=user.user_id,
                    action='login',
                    page='login',
                    timestamp=datetime.utcnow(),
                    user_agent=request.user_agent.string
                ))
                db_session.commit()

                # render appropriate template depending on role
                # NB: role is an enum, hence the .value
                role = user.role.value or 'student'

                if role == 'STUDENT':
                    
                    

                    #student_info = db_session.query(UserInfo).filter_by(user_id=session['id']).first()
                    user_id = session.get('id')
                    #if student_info and student_info.watched_demo and student_info.test_score is not None and student_info.test_score >= 80:
                    watched_video = db_session.query(Watched).filter_by(user_id=user_id).first()
                   
                    if watched_video:
                        if user.supervisor_id:
                            student_id=user.user_id
                            for model in [FormA, FormB, FormC]:
                                student_details = db_session.query(model).filter_by(user_id=student_id).first()
                                if student_details:
                                    return redirect(url_for('student_dashboard'))
                            return render_template('ethics_pack.html', name = session['name'])
                        elif not user.supervisor_id and user.authenticate_student and str(user.authenticate_student).lower() not in ['false', '0', 'none']:
                            return redirect(url_for('student_choose_supervisor'))
                        else:
                            flash("You are not yet Authenticated","danger")
                            return redirect(url_for('login_page'))
                    else:
                        if not user.supervisor_id and user.authenticate_student and str(user.authenticate_student).lower() not in ['false', '0', 'none']:
                            return redirect(url_for('student_choose_supervisor'))
                        
                        return render_template('video.html')
                elif role == 'SUPERVISOR':
                    session['supervisor_role']='SUPERVISOR'
                    return redirect(url_for('supervisor_dashboard'))
                elif role == 'ADMIN':
                    session['admin_role']='ADMIN'
                    return redirect(url_for('chair_landing'))
                elif role == 'REC':
                    session['rec_role']='REC'

                    return redirect(url_for('rec_dashboard'))
                elif role == 'REVIEWER':
                    session['reviewer_role']='REVIEWER'
                    session['supervisor_role']='REVIEWER'

                    return redirect(url_for('review_dashboard'))
                elif role == 'SUPER_ADMIN':
                    session['super_role']='SUPER_ADMIN'
                    return redirect(url_for('chair_landing'))
                else:
                    return render_template( 'video.html') #default fallback 
            else:
                error = 'Incorrect email or password'
                return render_template('login.html', messages=[error])
        else:
            error = 'Incorrect email or password'
            return render_template('login.html', messages=[error])

    return render_template('login.html')



###
###
### this is the function to focus on when intergrating MBA and Ethics
###
@app.route('/api/register', methods=['GET', 'POST'])
def register():
    try:
        msg = {}

        if request.method == 'POST':
            full_name = request.form.get('full_name', '').strip()
            student_number_raw = request.form.get('student_number', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()

            if password != confirm_password:
                msg = 'Passwords do not match.'
                return render_template('register.html', messages=[msg])

            # users.student_number is stored as Integer in the DB.
            # Validate early so bad input does not trigger DB rollback errors.
            if not student_number_raw.isdigit():
                msg = 'Student number must contain digits only.'
                return render_template('register.html', messages=[msg])
            student_number = int(student_number_raw)

            # Validate UJ email
            #if not email.endswith('student.uj.ac.za'):
                #msg = "Only University of Johannesburg email allowed"
                #return render_template('register.html', messages=[msg])

            # Validate password
            try:
                is_valid, message = validate_password(password)
                if not is_valid:
                    msg['message'] = message
                    return render_template('register.html', messages=[msg])
            except Exception as e:
                app.logger.error(f"Password validation error: {e}")
                return render_template('register.html', messages=["Invalid password. Please try again."])

            # Check if user exists
            try:
                user = db_session.query(User).filter_by(email=email).first()
                if user:
                    msg = 'Email already registered!'
                    return render_template('register.html', messages=[msg])
            except Exception as e:
                app.logger.error(f"DB lookup error: {e}")
                return render_template('register.html', messages=["Database error. Please try again later."])

            try:
                # Hash the password before storing (replace with proper hash function)
                # Example: password = generate_password_hash(password)

                # Create new user
                new_user = User(
                    full_name=full_name,
                    student_number=student_number,
                    email=email,
                    password=password,  # ⚠️ Replace with hashed version
                    role=UserRole.STUDENT
                )

                db_session.add(new_user)
                db_session.commit()

                stored_user = db_session.query(User).filter_by(email=email).first()

                # Send confirmation email
                try:
                    message = f'An account was created for this student number - {student_number}. Please wait for authentication before login.'
                    send_email(app, mail, message, [email])
                    msg = 'You have successfully registered!'
                except Exception as e:
                    app.logger.error(f"Email sending error: {e}")
                    msg = "Account created, but confirmation email could not be sent."

                flash("Account created successfully")
                return render_template("login.html", messages=[msg])

            except Exception as e:
                db_session.rollback()
                app.logger.error(f"User registration error: {e}")
                msg = 'Registration failed. Please try again.'
                return render_template('register.html', messages=[msg])

        return render_template('register.html', messages=[])

    except Exception as e:
        app.logger.error(f"Unexpected error in register route: {e}")
        return render_template('register.html', messages=["Unexpected error occurred. Please try again later."])


@app.route("/student_choose_supervisor",methods=['POST','GET'])
def student_choose_supervisor():
    user_id = session.get('id')
    if not user_id:
        flash("Your session has expired. Please log in again.", "danger")
        return redirect(url_for('login_page'))

    supervisors = db_session.query(User).filter(
        or_(
            User.role == UserRole.SUPERVISOR,
            User.role == UserRole.REVIEWER
        )
    ).all()

    user = db_session.query(User).filter_by(user_id=user_id).first()
    if not user:
        flash("Your account could not be found. Please log in again.", "danger")
        session.clear()
        return redirect(url_for('login_page'))

    if request.method == 'POST':
        supervisor_id = (request.form.get('supervisors') or '').strip()
        if not supervisor_id:
            flash("Please choose a supervisor before submitting.", "danger")
            return render_template('student_choose_supervisor.html', supervisors=supervisors)

        supervisor = db_session.query(User).filter_by(user_id=supervisor_id).first()
        if not supervisor:
            flash("The selected supervisor could not be found. Please choose again.", "danger")
            return render_template('student_choose_supervisor.html', supervisors=supervisors)

        user.supervisor_id = supervisor_id
        db_session.commit()

        if user.supervisor_id:
            # Sending email should not break supervisor assignment.
            try:
                message = (
                    f'You have been assigned to be the supervisor of the student with the '
                    f'name {user.full_name} and student number- {user.student_number}.'
                )
                send_email(app, mail, message, [supervisor.email])
            except Exception as e:
                print("Email sending error:", str(e))

            return render_template('video.html', name=session.get('name', user.full_name))

    return render_template('student_choose_supervisor.html', supervisors=supervisors)


def sync_student_supervisor_forms(student, supervisor):
    updated_counts = {"form_a": 0, "form_b": 0, "form_c": 0}

    form_a_records = db_session.query(FormA).filter_by(user_id=student.user_id).all()
    for form in form_a_records:
        form.supervisor = supervisor.full_name
        form.supervisor_email = supervisor.email
        updated_counts["form_a"] += 1

    form_b_records = db_session.query(FormB).filter_by(user_id=student.user_id).all()
    for form in form_b_records:
        form.supervisor = supervisor.full_name
        form.supervisor_email = supervisor.email
        updated_counts["form_b"] += 1

    form_c_records = db_session.query(FormC).filter_by(user_id=student.user_id).all()
    for form in form_c_records:
        form.supervisor_name = supervisor.full_name
        form.supervisor_email = supervisor.email
        updated_counts["form_c"] += 1

    return updated_counts


def has_review_feedback_started(form):
    return bool(
        getattr(form, 'form_reviewed_by', None)
        or getattr(form, 'form_reviewed_by1', None)
        or getattr(form, 'review_status', None)
        or getattr(form, 'review_status1', None)
    )


def can_reassign_reviewers(form):
    return True


def get_form_submission_timestamp(form, form_type):
    if form_type == 'FORM A':
        return getattr(form, 'submitted_at', None) or getattr(form, 'created_at', None)
    if form_type == 'FORM B':
        return getattr(form, 'submitted_at', None) or getattr(form, 'created_at', None)
    return getattr(form, 'submission_date', None) or getattr(form, 'created_at', None)


def get_latest_forms_for_reviewer_reassignment():
    latest_forms = []

    form_configs = [
        ('FORM A', FormA, func.coalesce(FormA.submitted_at, FormA.created_at)),
        ('FORM B', FormB, func.coalesce(FormB.submitted_at, FormB.created_at)),
        ('FORM C', FormC, func.coalesce(FormC.submission_date, FormC.created_at)),
    ]

    for form_type, model, order_column in form_configs:
        records = (
            db_session.query(model)
            .filter(
                or_(
                    getattr(model, 'submitted_to_admin') == True,
                    getattr(model, 'submitted_to_reviewers') == True,
                )
            )
            .order_by(desc(order_column))
            .all()
        )

        latest_by_user = {}
        for record in records:
            if record.user_id not in latest_by_user:
                latest_by_user[record.user_id] = record

        for record in latest_by_user.values():
            latest_forms.append((form_type, record))

    latest_forms.sort(
        key=lambda item: get_form_submission_timestamp(item[1], item[0]) or datetime.min,
        reverse=True
    )
    return latest_forms


def build_reviewer_reassignment_rows(form_records, reviewer_lookup, student_lookup):
    rows = []

    for form_type, form in form_records:
        reviewer_ids = [
            reviewer_id for reviewer_id in
            [getattr(form, 'reviewer_name1', None), getattr(form, 'reviewer_name2', None)]
            if reviewer_id
        ]
        assigned_reviewers = [
            reviewer_lookup[reviewer_id]
            for reviewer_id in reviewer_ids
            if reviewer_id in reviewer_lookup
        ]
        student = student_lookup.get(form.user_id)
        rows.append({
            'form_id': form.form_id,
            'form_type': form_type,
            'user_id': form.user_id,
            'student_name': getattr(form, 'applicant_name', None) or (student.full_name if student else 'Unknown Student'),
            'student_number': getattr(form, 'student_number', None) or (student.student_number if student else None),
            'student_email': (
                getattr(form, 'email', None)
                or getattr(form, 'email_address', None)
                or (student.email if student else None)
            ),
            'submitted_at': get_form_submission_timestamp(form, form_type),
            'assigned_reviewers': assigned_reviewers,
            'selected_reviewer_ids': reviewer_ids,
            'can_reassign': can_reassign_reviewers(form),
            'review_started': has_review_feedback_started(form),
            'view_url': url_for('chair_form_view', id=form.form_id, form_name=form_type),
        })

    return rows


def generate_temporary_password(length=12):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    specials = "!@#$%^&*"

    while True:
        core_length = max(length - 1, 5)
        password_chars = [secrets.choice(alphabet) for _ in range(core_length)]
        password_chars.append(secrets.choice(specials))
        secrets.SystemRandom().shuffle(password_chars)
        candidate = ''.join(password_chars)
        is_valid, _ = validate_password(candidate)
        if is_valid:
            return candidate


def _pdf_escape(text):
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def build_simple_text_pdf(lines, title="Document"):
    page_width = 612
    page_height = 792
    margin_left = 50
    top_y = 760
    line_height = 18
    lines_per_page = 36

    pages = []
    for start in range(0, len(lines), lines_per_page):
        pages.append(lines[start:start + lines_per_page])

    if not pages:
        pages = [[""]]

    objects = []

    def add_object(payload):
        objects.append(payload)
        return len(objects)

    font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    title_font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    page_ids = []
    content_ids = []
    pages_placeholder_index = len(objects)
    objects.append(None)

    for page_lines in pages:
        content_stream_lines = [
            "BT",
            f"/F2 18 Tf",
            f"1 0 0 1 {margin_left} {top_y} Tm",
            f"({_pdf_escape(title)}) Tj",
        ]

        current_y = top_y - 34
        for line in page_lines:
            content_stream_lines.extend([
                f"/F1 12 Tf",
                f"1 0 0 1 {margin_left} {current_y} Tm",
                f"({_pdf_escape(line)}) Tj",
            ])
            current_y -= line_height

        content_stream_lines.append("ET")
        content_stream = "\n".join(content_stream_lines)
        content_id = add_object(
            f"<< /Length {len(content_stream.encode('latin-1', errors='replace'))} >>\nstream\n"
            f"{content_stream}\nendstream"
        )
        content_ids.append(content_id)

        page_id = add_object(
            "<< /Type /Page /Parent {parent} 0 R "
            f"/MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 {font_id} 0 R /F2 {title_font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        )
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_placeholder_index] = (
        f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>"
    )
    pages_id = pages_placeholder_index + 1

    for page_id in page_ids:
        objects[page_id - 1] = objects[page_id - 1].replace("{parent}", str(pages_id))

    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    pdf_parts = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]

    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in pdf_parts))
        pdf_parts.append(f"{index} 0 obj\n{obj}\nendobj\n".encode("latin-1", errors="replace"))

    xref_position = sum(len(part) for part in pdf_parts)
    pdf_parts.append(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf_parts.append(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf_parts.append(f"{offset:010d} 00000 n \n".encode("latin-1"))

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF"
    )
    pdf_parts.append(trailer.encode("latin-1"))
    return b"".join(pdf_parts)


def build_student_password_pdf(student, password, admin_user):
    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines = [
        "Student Password Reset Confirmation",
        "",
        f"Student Name: {student.full_name}",
        f"Student Number: {student.student_number or 'N/A'}",
        f"Student Email: {student.email}",
        "",
        f"New Password: {password}",
        "",
        f"Generated By: {admin_user.full_name}",
        f"Generated At: {generated_at}",
        "",
        f"Login Link: {web_url}",
        "",
        "Please keep this document secure and share it only with the intended student.",
    ]
    return build_simple_text_pdf(lines, title="UJ Ethics Password Reset")


@app.route('/admin/reassign_supervisors', methods=['GET', 'POST'])
def admin_reassign_supervisors():
    admin_id = session.get('id')
    if not admin_id:
        flash("Your session has expired. Please log in again.", "danger")
        return redirect(url_for('login_page'))

    user_profile = db_session.query(User).filter_by(user_id=admin_id).first()
    if not user_profile:
        session.clear()
        flash("Your account could not be found. Please log in again.", "danger")
        return redirect(url_for('login_page'))

    role = user_profile.role.value if user_profile.role else ''
    if role not in ['ADMIN', 'SUPER_ADMIN']:
        flash("You are not authorized to access that page.", "danger")
        return redirect(url_for('login_page'))

    supervisors = db_session.query(User).filter(
        or_(
            User.role == UserRole.SUPERVISOR,
            User.role == UserRole.REVIEWER
        )
    ).order_by(User.full_name.asc()).all()

    if request.method == 'POST':
        page = request.form.get('page', 1, type=int)
        student_id = (request.form.get('student_id') or '').strip()
        supervisor_id = (request.form.get('supervisor_id') or '').strip()

        student = db_session.query(User).filter_by(user_id=student_id).first()
        if not student or student.role != UserRole.STUDENT:
            flash("The selected student could not be found.", "danger")
            return redirect(url_for('admin_reassign_supervisors', page=page))

        if not supervisor_id:
            flash("Please choose a supervisor before saving.", "danger")
            return redirect(url_for('admin_reassign_supervisors', page=page))

        supervisor = db_session.query(User).filter_by(user_id=supervisor_id).first()
        if not supervisor or supervisor.role not in [UserRole.SUPERVISOR, UserRole.REVIEWER]:
            flash("The selected supervisor could not be found.", "danger")
            return redirect(url_for('admin_reassign_supervisors', page=page))

        student.supervisor_id = supervisor.user_id
        updated_counts = sync_student_supervisor_forms(student, supervisor)

        db_session.add(UserActivityLog(
            user_id=admin_id,
            action='admin_reassign_supervisor',
            page=request.path,
            target_user_id=student.user_id,
            timestamp=datetime.now(),
            details=(
                f"Reassigned supervisor for {student.full_name} ({student.email}) "
                f"to {supervisor.full_name} ({supervisor.email}). "
                f"Updated forms: A={updated_counts['form_a']}, "
                f"B={updated_counts['form_b']}, C={updated_counts['form_c']}"
            )
        ))

        db_session.commit()

        try:
            message = (
                f'You have been assigned to be the supervisor of the student with the '
                f'name {student.full_name} and student number- {student.student_number}.'
            )
            send_email(app, mail, message, [supervisor.email])
        except Exception as e:
            print("Email sending error:", str(e))

        flash(
            f"Supervisor updated for {student.full_name}. "
            f"Student forms synced: Form A ({updated_counts['form_a']}), "
            f"Form B ({updated_counts['form_b']}), Form C ({updated_counts['form_c']}).",
            "success"
        )
        return redirect(url_for('admin_reassign_supervisors', page=page))

    page = request.args.get('page', 1, type=int)
    per_page = 15
    students_query = db_session.query(User).filter(
        User.role == UserRole.STUDENT
    ).order_by(User.full_name.asc())
    total_students = students_query.count()
    students = students_query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total_students + per_page - 1) // per_page
    supervisor_lookup = {supervisor.user_id: supervisor for supervisor in supervisors}

    return render_template(
        'admin_reassign_supervisors.html',
        role=role,
        user_profile=user_profile,
        students=students,
        supervisors=supervisors,
        supervisor_lookup=supervisor_lookup,
        page=page,
        total_pages=total_pages
    )


@app.route('/admin/reassign_reviewers', methods=['GET', 'POST'])
def admin_reassign_reviewers():
    admin_id = session.get('id')
    if not admin_id:
        flash("Your session has expired. Please log in again.", "danger")
        return redirect(url_for('login_page'))

    user_profile = db_session.query(User).filter_by(user_id=admin_id).first()
    if not user_profile:
        session.clear()
        flash("Your account could not be found. Please log in again.", "danger")
        return redirect(url_for('login_page'))

    role = user_profile.role.value if user_profile.role else ''
    if role not in ['ADMIN', 'SUPER_ADMIN']:
        flash("You are not authorized to access that page.", "danger")
        return redirect(url_for('login_page'))

    reviewers = (
        db_session.query(User)
        .filter(User.role == UserRole.REVIEWER)
        .order_by(User.full_name.asc())
        .all()
    )
    reviewer_lookup = {reviewer.user_id: reviewer for reviewer in reviewers}

    if request.method == 'POST':
        page = request.form.get('page', 1, type=int)
        form_id = (request.form.get('form_id') or '').strip()
        form_type = (request.form.get('form_type') or '').strip().upper()
        reviewer1_id = (request.form.get('reviewer_1_id') or '').strip()
        reviewer2_id = (request.form.get('reviewer_2_id') or '').strip()

        form_model_map = {
            'FORM A': FormA,
            'FORM B': FormB,
            'FORM C': FormC,
        }
        model = form_model_map.get(form_type)
        if not model:
            flash("The selected form type is invalid.", "danger")
            return redirect(url_for('admin_reassign_reviewers', page=page))

        form = db_session.query(model).filter_by(form_id=form_id).first()
        if not form:
            flash("The selected form could not be found.", "danger")
            return redirect(url_for('admin_reassign_reviewers', page=page))

        selected_ids = []
        for reviewer_id in [reviewer1_id, reviewer2_id]:
            if reviewer_id and reviewer_id not in selected_ids:
                selected_ids.append(reviewer_id)

        if len(selected_ids) < 1 or len(selected_ids) > 2:
            flash("Please choose one or two different reviewers before saving.", "danger")
            return redirect(url_for('admin_reassign_reviewers', page=page))

        selected_reviewers = (
            db_session.query(User)
            .filter(
                User.user_id.in_(selected_ids),
                User.role == UserRole.REVIEWER
            )
            .order_by(User.full_name.asc())
            .all()
        )
        if len(selected_reviewers) != len(selected_ids):
            flash("One or more selected reviewers could not be found.", "danger")
            return redirect(url_for('admin_reassign_reviewers', page=page))

        form.reviewer_name1 = selected_ids[0]
        form.reviewer_name2 = selected_ids[1] if len(selected_ids) > 1 else None
        form.submitted_to_reviewers = True

        db_session.add(UserActivityLog(
            user_id=admin_id,
            action='admin_reassign_reviewers',
            page=request.path,
            target_user_id=form.user_id,
            timestamp=datetime.now(),
            details=(
                f"Reassigned reviewers for {form_type} {form.form_id} to "
                f"{', '.join(selected_ids)}"
            )
        ))
        db_session.commit()

        try:
            reviewer_emails = [reviewer.email for reviewer in selected_reviewers if reviewer.email]
            if reviewer_emails:
                message = (
                    f'You have been assigned as a reviewer for {form_type} '
                    f'belonging to {getattr(form, "applicant_name", "a student")}. '
                    f'Please log into the ethics application system and review the form.'
                )
                send_email(app, mail, message, reviewer_emails)
        except Exception as e:
            print("Email sending error:", str(e))

        flash(
            f"Reviewers updated for {getattr(form, 'applicant_name', 'the selected student')} ({form_type}).",
            "success"
        )
        return redirect(url_for('admin_reassign_reviewers', page=page))

    page = request.args.get('page', 1, type=int)
    per_page = 15
    form_records = get_latest_forms_for_reviewer_reassignment()
    student_ids = list({form.user_id for _, form in form_records})
    students = db_session.query(User).filter(User.user_id.in_(student_ids)).all() if student_ids else []
    student_lookup = {student.user_id: student for student in students}
    rows = build_reviewer_reassignment_rows(form_records, reviewer_lookup, student_lookup)

    total_forms = len(rows)
    total_pages = (total_forms + per_page - 1) // per_page if total_forms else 1
    start_index = (page - 1) * per_page
    paginated_rows = rows[start_index:start_index + per_page]

    return render_template(
        'admin_reassign_reviewers.html',
        role=role,
        user_profile=user_profile,
        reviewer_rows=paginated_rows,
        reviewers=reviewers,
        page=page,
        total_pages=total_pages
    )


@app.route('/admin/student-password-resets', methods=['GET', 'POST'])
@role_required('ADMIN', 'SUPER_ADMIN')
def admin_student_password_resets():
    admin_id = session.get('id')
    user_profile = db_session.query(User).filter_by(user_id=admin_id).first() if admin_id else None

    if not user_profile:
        flash("Session expired. Please login again.", "danger")
        return redirect(url_for('login_page'))

    role = user_profile.role.value if user_profile.role else ''

    if request.method == 'POST':
        page = request.form.get('page', 1, type=int)
        search_query = (request.form.get('search') or '').strip()
        student_id = (request.form.get('student_id') or '').strip()
        provided_password = (request.form.get('new_password') or '').strip()

        student = db_session.query(User).filter_by(user_id=student_id).first()
        if not student or student.role != UserRole.STUDENT:
            flash("The selected student could not be found.", "danger")
            return redirect(url_for('admin_student_password_resets', page=page, search=search_query))

        new_password = provided_password or generate_temporary_password()
        is_valid, message = validate_password(new_password)
        if not is_valid:
            flash(message, "danger")
            return redirect(url_for('admin_student_password_resets', page=page, search=search_query))

        try:
            student.password = new_password
            db_session.add(UserActivityLog(
                user_id=admin_id,
                action='admin_reset_student_password',
                page=request.path,
                target_user_id=student.user_id,
                timestamp=datetime.now(),
                details=(
                    f"Admin reset password for {student.full_name} ({student.email}). "
                    f"PDF credential sheet generated."
                )
            ))
            db_session.commit()
        except Exception as e:
            db_session.rollback()
            app.logger.error(f"Student password reset failed: {e}")
            flash("Password reset failed. Please try again.", "danger")
            return redirect(url_for('admin_student_password_resets', page=page, search=search_query))

        pdf_bytes = build_student_password_pdf(student, new_password, user_profile)
        safe_name = secure_filename(student.full_name or 'student')
        filename = f"{safe_name or 'student'}_new_password.pdf"

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    page = request.args.get('page', 1, type=int)
    per_page = 15
    search_query = (request.args.get('search') or '').strip()

    students_query = db_session.query(User).filter(User.role == UserRole.STUDENT)
    if search_query:
        search_term = f"%{search_query}%"
        students_query = students_query.filter(
            or_(
                User.full_name.ilike(search_term),
                User.email.ilike(search_term),
                cast(User.student_number, String).ilike(search_term)
            )
        )

    students_query = students_query.order_by(User.full_name.asc())
    total_students = students_query.count()
    students = students_query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total_students + per_page - 1) // per_page)

    return render_template(
        'admin_student_password_resets.html',
        role=role,
        user_profile=user_profile,
        students=students,
        page=page,
        total_pages=total_pages,
        search_query=search_query
    )


@app.route("/authenticate_student/<string:id>",methods=['POST','GET'])
@role_required('ADMIN', 'SUPER_ADMIN')
def authenticate_student(id):
    if request.method=='POST':
        try:
            user=db_session.query(User).filter_by(user_id=id).first()
            admin_id = session.get('id')
            if user:
                print(f"Authenticating student: {user.full_name}")
                user.authenticate_student='true'
                # Log admin action
                db_session.add(UserActivityLog(
                    user_id=admin_id,
                    action='admin_authenticate_user',
                    page=request.path,
                    target_user_id=user.user_id,
                    timestamp=datetime.now(),
                    details=f"Admin authenticated user: {user.full_name} ({user.email})"
                ))
                # Commit the authentication change to database
                db_session.commit()
                print(f"Student {user.full_name} authenticated successfully in database.")
                # Send email notification (separate from database transaction)
                message=(f'Your account has been authenticated. Please follow the link to login '
                f'{web_url}')
                try:
                    send_email(app,mail, message,[user.email])
                    print(f"Authentication email sent to {user.email}")
                except Exception as e:
                    print("Email sending error:", str(e))
                
                return redirect(url_for('all_users'))
            else:
                flash("no such student on our data")
                return redirect(url_for("all_users"))
        except Exception as e:
            print(f"Error authenticating student: {str(e)}")
            db_session.rollback()
            flash("Error authenticating student")
            return redirect(url_for("all_users"))
    return redirect(url_for('all_users')) 



@app.route("/diactivate_user_account/<string:id>",methods=['POST','GET'])
@role_required('ADMIN', 'SUPER_ADMIN')
def diactivate_user_account(id):
    if request.method=='POST':
        try:
            user=db_session.query(User).filter_by(user_id=id).first()
            admin_id = session.get('id')
            if user:
                print(f"Deactivating user account: {user.full_name}")
                user.authenticate_student='false'
                # Log admin action
                db_session.add(UserActivityLog(
                    user_id=admin_id,
                    action='admin_deactivate_user',
                    page=request.path,
                    target_user_id=user.user_id,
                    timestamp=datetime.now(),
                    details=f"Admin deactivated user: {user.full_name} ({user.email})"
                ))
                # Commit the authentication change to database
                db_session.commit()
                print(f"Student {user.full_name} deactivated successfully in database.")
                # Send email notification (separate from database transaction)
                message=(f'Your account has been deactivated. To stay active please contact Ethics support team'
                f'{web_url}')
                try:
                    send_email(app,mail, message,[user.email])
                    print(f"Deactivation email sent to {user.email}")
                except Exception as e:
                    print("Email sending error:", str(e))
                
                return redirect(url_for('all_users'))
            else:
                flash("no such student on our data")
                return redirect(url_for("all_users"))
        except Exception as e:
            print(f"Error deactivating student: {str(e)}")
            db_session.rollback()
            flash("Error deactivating student")
            return redirect(url_for("all_users"))
    return redirect(url_for('all_users'))


@app.route('/register_reviewer', methods=['GET', 'POST'])
@role_required('ADMIN', 'SUPER_ADMIN')
def register_reviewer():
    
    messages=''
    if request.method == 'POST':
        full_name = request.form.get('full_name', '')
        staff_number = request.form.get('staff_number', '')
        email = request.form.get('email', '').lower()
        password = request.form.get('password', '')
        password2=request.form.get('password2')
        specialisation = request.form.get('specialisation')
        role=request.form.get('role')
        if password == password2:

            # Validate password
            is_valid, message = validate_password(password)
            if not is_valid:
                return render_template('register_reviewer.html', messages=[message])

            # Check if user exists
            user = db_session.query(User).filter_by(email=email).first()
            if user:
                messages = 'Email already registered!'
                return render_template('register_reviewer.html', messages=[messages])
            
            try:
                # Hash the password properly
                
                # Create new user
                new_user = User(
                    full_name=full_name,
                    staff_number=staff_number,
                    email=email,
                    password=password,  # Make sure this is the hashed version
                    specialisation=specialisation,
                    role=role
                )
                
                db_session.add(new_user)
                db_session.commit()
                #sending email to the reviewers
                ###
                ### uncomment the code bellow for real testing

                
                try:
                    message=(f'An account was created on your behalf. ' 
                    f'Please follow the link {web_url} use your '
                    f' email as username and password is = {password}')
                    send_email(app,mail, message,[email])
                    messages = 'You have successfully registered!'
                except Exception as e:
                    print("Email sending error:", str(e))
                return redirect(url_for('reviewer_list'))
                
            except Exception as e:
                db_session.rollback()
                print("Registration error:", str(e))
                messages = 'Registration failed. Please try again.'
                return render_template('register_reviewer.html', messages=[messages])
        else:
            messages="Passwords mismatch"
            render_template('register_reviewer.html', messages=[messages])
    messages= 'Please fill out the form completely!'
    return render_template('register_reviewer.html', messages=[messages])


@app.route('/super_admin_registration', methods=['GET', 'POST'])
@role_required('SUPER_ADMIN')
def super_admin_registration():
    messages = ''

    if request.method == 'POST':
        full_name = request.form.get('full_name', '')
        staff_number = request.form.get('staff_number', '')
        email = request.form.get('email', '').lower()
        password = request.form.get('password', '')
        password2 = request.form.get('password2')
        specialisation = request.form.get('specialisation')
        role = request.form.get('super_admin')

        if password != password2:
            messages = "Passwords mismatch"
            return render_template(
                'super_admin_registration.html',
                messages=[messages]
            )

        # Validate password
        is_valid, message = validate_password(password)
        if not is_valid:
            return render_template(
                'super_admin_registration.html',
                messages=[message]
            )

        # Check if user exists
        user = db_session.query(User).filter_by(email=email).first()
        if user:
            messages = 'Email already registered!'
            return render_template(
                'super_admin_registration.html',
                messages=[messages]
            )

        try:
            # Create new user
            new_user = User(
                full_name=full_name,
                staff_number=staff_number,
                email=email,
                password=password,  # 🔒 TODO: hash properly with bcrypt
                specialisation=specialisation,
                role=role
            )

            db_session.add(new_user)
            db_session.commit()

            # Prepare and send email
            message = (
                f'You have successfully created an account. '
                f'Please follow the link {web_url} '
                f'use your email as username and password is= {password}'
            )
            try:
                send_email(app, mail, message, [email])
            except Exception as e:
                print("Email sending error:", str(e))

            return redirect(url_for('login_page'))

        except Exception as e:
            db_session.rollback()
            error_trace = traceback.format_exc()  # full traceback
            print("Registration error:", str(e))
            print(error_trace)

            # Instead of generic template, return JSON so you see exact error
            return jsonify({
                "status": "error",
                "message": str(e),
                "trace": error_trace
            }), 500

    return render_template(
        'super_admin_registration.html',
        messages=['Please fill out the form completely!']
    )



###
###
### this is the function to focus on when intergrating MBA and Ethics
###
@app.route('/edit_user/<string:id>', methods=['POST','GET'])
@role_required('ADMIN', 'SUPER_ADMIN')
def edit_user(id):
    """
    Edit a user's profile. Only apply changes for fields that are provided and non-empty.
    - Leave existing DB values unchanged when inputs are blank on the frontend.
    - Change password only if both password and password2 are provided, match, and pass validation.
    - Avoid clobbering template 'role' with the posted role by using separate variables.
    """
    user = db_session.query(User).filter_by(user_id=id).first()
    user_id = session.get('id')
    user_profile = db_session.query(User).filter_by(user_id=user_id).first() if user_id else None
    current_role = user_profile.role.value if user_profile and user_profile.role else None

    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('all_users'))

    if request.method == "POST":
        # Read form values and strip whitespace; treat empty strings as "not provided"
        full_name = (request.form.get('full_name') or '').strip()
        staff_number = (request.form.get('staff_number') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        new_password = (request.form.get('password') or '').strip()
        confirm_password = (request.form.get('password2') or '').strip()
        specialisation = (request.form.get('specialisation') or '').strip()
        new_role_raw = (request.form.get('role') or '').strip()

        try:
            changed = False
            password_was_changed = False

            # Apply non-empty field updates only
            if full_name:
                if user.full_name != full_name:
                    user.full_name = full_name
                    changed = True

            if staff_number:
                if getattr(user, 'staff_number', None) != staff_number:
                    user.staff_number = staff_number
                    changed = True

            if email:
                if user.email != email:
                    user.email = email
                    changed = True

            if specialisation:
                if getattr(user, 'specialisation', None) != specialisation:
                    user.specialisation = specialisation
                    changed = True

            # Role mapping (optional). Only update if a value was provided.
            if new_role_raw:
                new_role_value = None
                try:
                    # Try mapping by enum name (e.g., 'ADMIN')
                    new_role_value = UserRole[new_role_raw.upper()]
                except Exception:
                    # Try mapping by enum value string (case-insensitive)
                    try:
                        for m in UserRole:
                            if str(m.value).lower() == new_role_raw.lower():
                                new_role_value = m
                                break
                    except Exception:
                        new_role_value = None

                if new_role_value is not None:
                    if user.role != new_role_value:
                        user.role = new_role_value
                        changed = True
                else:
                    # If we can't map to enum, as a conservative choice do not change role
                    pass

            # Password behavior:
            # - If no new password is provided, keep the current password unchanged.
            # - If new password is provided, update password.
            # - If confirm field is also provided, it must match.
            if new_password:
                if confirm_password and new_password != confirm_password:
                    flash('Passwords do not match', 'danger')
                    return redirect(url_for('edit_user', id=user.user_id))

                old_password_hash = user.password
                print(f"[EDIT_USER DEBUG] User {user.user_id} old password-column hash: {old_password_hash}")

                # Use model setter: hashes and stores into DB column `password`
                user.password = new_password
                print(f"[EDIT_USER DEBUG] User {user.user_id} new password-column hash (pre-flush): {user.password}")
                changed = True

                # Ensure the new hash is written and immediately verifiable before final commit
                db_session.flush()
                print(f"[EDIT_USER DEBUG] User {user.user_id} password-column hash after flush: {user.password}")
                if not user.verify_password(new_password):
                    db_session.rollback()
                    flash('Password update failed. Please try again.', 'danger')
                    return redirect(url_for('edit_user', id=user.user_id))
                print(f"[EDIT_USER DEBUG] User {user.user_id} verify new password: True")
                password_was_changed = True
            elif confirm_password:
                flash('Enter a new password before confirming it.', 'danger')
                return redirect(url_for('edit_user', id=user.user_id))

            if changed:
                db_session.commit()
                print(f"[EDIT_USER DEBUG] User {user.user_id} commit successful")

                if password_was_changed:
                    try:
                        notify_msg = (
                            f'Your profile was changed on your behalf. '
                            f'Please follow the link {web_url} use your '
                            f'email as username and password is = {new_password}'
                        )
                        send_email(app, mail, notify_msg, [user.email])
                    except Exception as e:
                        app.logger.error(f"Failed to send email to {user.email}: {e}")

                flash('User details updated successfully.', 'success')
                return redirect(url_for('edit_user', id=user.user_id))
            else:
                flash('No changes to update.', 'info')
                return redirect(url_for('edit_user', id=user.user_id))

        except Exception as e:
            db_session.rollback()
            app.logger.error(f"Update error: {e}")
            flash('Update failed. Please try again.', 'danger')
            return redirect(url_for('edit_user', id=user.user_id))

    
    if not user_profile:
        flash("Session expired. Please login again.")
        return redirect(url_for('login_page'))

    role = user_profile.role.value
    return render_template(
        'edit_user.html',
        role=role,
        user_profile=user_profile,
        user=user,
        current_role=current_role
    )


@app.route('/admin/upload_student_docs', methods=['GET', 'POST'])
@app.route('/admin/upload_student_docs/<string:id>', methods=['GET', 'POST'])
@csrf.exempt
@role_required('ADMIN', 'SUPER_ADMIN')
def admin_upload_student_docs(id=None):
    # Fetch all requirement records with distinct user_id to avoid duplicates
    all_requirements = db_session.query(FormARequirements).distinct(FormARequirements.user_id).all()
    
    # Join with form tables to get applicant_name using form_id
    for req in all_requirements:
        student_name = None
        
        # Try to get applicant_name from FormA using form_id
        if req.form_type == 'FormA' or not student_name:
            form_a = db_session.query(FormA).filter_by(user_id=req.user_id).first()
            if form_a and form_a.applicant_name:
                student_name = form_a.applicant_name
        
        # Try to get applicant_name from FormB using form_id
        if not student_name and (req.form_type == 'FormB' or not student_name):
            form_b = db_session.query(FormB).options(
                defer(FormB.permission_letter),
                defer(FormB.prior_clearance),
                defer(FormB.ethics_evidence),
                defer(FormB.proposal_path),
                defer(FormB.pending_note),
                defer(FormB.private_permission_file)
            ).filter_by(user_id=req.user_id).first()
            if form_b and form_b.applicant_name:
                student_name = form_b.applicant_name
        
        # Try to get applicant_name from FormC using form_id
        if not student_name and (req.form_type == 'FormC' or not student_name):
            form_c = db_session.query(FormC).filter_by(user_id=req.user_id).first()
            if form_c and form_c.applicant_name:
                student_name = form_c.applicant_name
        
        req.student_name = student_name if student_name else f"Unknown (ID: {req.user_id})"
    
    # Optional: fetch user info for the sidebar if needed by the layout
    current_uid = session.get('id')
    current_user = db_session.query(User).filter_by(user_id=current_uid).first() if current_uid else None

    if request.method == 'POST':
        # Get the ID of the FormARequirements record (not User ID)
        record_id = request.form.get('id') or id
        form_type = request.form.get('form_type')
        
        if not record_id:
            flash("No Requirement ID provided. Please select one from the dropdown.", "warning")
            return redirect(url_for('admin_upload_student_docs'))

        # Locate the record by its Primary Key
        req = db_session.query(FormARequirements).filter_by(id=record_id).first()
        if not req:
            flash(f"Requirement record with ID '{record_id}' does not exist.", "danger")
            return redirect(url_for('admin_upload_student_docs'))
        
        req.form_type = form_type

        # Handle Booleans
        bool_fields = ['needs_permission', 'has_clearance', 'company_requires_jbs', 'has_ethics_evidence', 'ethics_evidence']
        for b_field in bool_fields:
            setattr(req, b_field, b_field in request.form)

        # Mapping for inconsistent filename columns in models.py
        filename_mapping = {
            'research_tools_path': 'research_tools_filename',
            'proposal_path': 'proposal_filename',
            'impact_assessment_path': 'impact_assessment_filename',
            'participation_info_sheet': 'participation_info_filename',
            'prior_clearance_path': 'prior_clearance_path_filename',
            'ethics_evidence_path': 'ethics_evidence_path_filename'
        }

        # List of binary fields
        file_fields = [
            'needs_permission_pending', 'pending_note', 'permission_letter',
            'prior_clearance_path', 'prior_clearance', 'prior_clearance1',
            'need_jbs_clearance', 'need_jbs_clearance1', 'research_tools_path',
            'proposal_path', 'impact_assessment_path', 'participation_info_sheet',
            'ethics_evidence_path', 'files'
        ]

        uploaded_any = False
        for field in file_fields:
            file_obj = request.files.get(field)
            if file_obj and file_obj.filename:
                file_data = file_obj.read()
                setattr(req, field, file_data)
                
                # Determine filename column
                fname_col = filename_mapping.get(field, f"{field}_filename")
                setattr(req, fname_col, file_obj.filename)
                uploaded_any = True
        
        if uploaded_any:
            req.updated_at = datetime.now()
        
        try:
            db_session.commit()
            if uploaded_any:
                flash(f"Successfully uploaded documents and updated flags for ID: {record_id}", "success")
            else:
                flash(f"Updated status flags for ID: {record_id}", "success")
        except Exception as e:
            db_session.rollback()
            flash(f"Error saving database changes: {str(e)}", "danger")

        return redirect(url_for('admin_upload_student_docs'))

    return render_template("admin_upload_docs.html", 
                         requirements=all_requirements, 
                         user_profile=current_user, 
                         role='super_admin')


@app.route('/super_admin', methods=['GET', 'POST'])
def super_admin():
    user_id=session.get('id')
   
    
    user=db_session.query(User).filter(User.user_id==user_id).first()
    user_profile=db_session.query(User).filter_by(user_id=user_id).first()
    all_users = db_session.query(User).all()

    role=user.role.value
    return render_template("superadmin_dashboard.html",role=role,user_profile=user_profile,all_users=all_users,current_year=datetime.now().year)



### Enhanced Analytics Dashboard
### Form A Analytics with Professional Visualizations
from data_ploting import (plot_risk_rating_distribution_a,
plot_review_recommendations_a,
plot_supervisor_recommendations_a,
plot_rec_member_distribution_a,
plot_certificate_status_a,
plot_submissions_over_time_a,
plot_review_by_risk_rating_a,
plot_top_applicants_a,
plot_certificate_received_percentage_a,
plot_review_recommendation_comparison_a,
plot_applications_vs_certificates_a,
calculate_kpis_a,
create_sunburst_chart_a)

from enhanced_analytics import analytics
@app.route('/super_admin_form_a', methods=['GET', 'POST'])
def super_admin_form_a():
    user_id = session.get('id')
    if not user_id:
        return redirect(url_for('login_page'))
    user = db_session.query(User).filter(User.user_id==user_id).first()
    if not user:
        return redirect(url_for('login_page'))
    role = user.role.value

    forma = 'A'

    # Enhanced data collection with additional fields for better analytics
    forms_list = [
    {
        "id": form.form_id,
        "applicant_name": form.applicant_name,
        "submitted_at": form.submitted_at,
        "risk_rating": form.risk_rating or 'Not Assessed',
        "supervisor": form.supervisor,
        "ethics_signature_date": form.supervisor_date,
        "supervisor_recommendation": form.recommendation,
        "first_reviewer_name": form.form_reviewed_by,
        "second_reviewer_name": form.form_reviewed_by1,
        "review_signature_date": form.review_signature_date,
        "review_recommendation": form.review_recommendation,
        "review_signature_date1": form.review_signature_date1,
        "review_recommendation1": form.review_recommendation1,
        "certificate_issued": form.certificate_issued,
        "certificate_received": form.certificate_received,
        "first_reviewer": form.reviewer_name1,
        "second_reviewer": form.reviewer_name2,
        "submitted_to_rec": form.submitted_to_rec if rec else False,
        "rec_full_name": rec.full_name if rec else None,
        "student_number": form.student_number,
        "department": form.department,
        "degree": form.degree
    }
    for form, rec in (
        db_session.query(FormA, Rec)
        .outerjoin(Rec, FormA.form_id == Rec.form_id)
        .filter(FormA.submitted_at.isnot(None))  # Only include submitted forms
        .order_by(FormA.submitted_at.desc())
        .limit(200)  # Increased limit for better analytics
        .all()
    )
    ]
    
    # Debug log
    app.logger.info(f"Found {len(forms_list)} Form A submissions for analytics")
    
    if forms_list:
        df = pd.DataFrame(forms_list)
        
        # Calculate KPIs
        kpis = calculate_kpis_a(df)
        
        # Create enhanced visualizations with error handling
        context = {"kpis": kpis}
        
        try:
            context.update({
                # Interactive Plotly charts
                "sunburst_chart": create_sunburst_chart_a(df),
                "interactive_timeline": analytics.create_interactive_timeline(df, 'A'),
                "risk_analysis": analytics.create_advanced_risk_analysis(df, 'A'),
                "reviewer_performance": analytics.create_reviewer_performance_dashboard(df, 'A'),
                
                # Enhanced matplotlib charts
                "risk_rating_distribution": plot_risk_rating_distribution_a(df),
                "review_recommendations": plot_review_recommendations_a(df),
                "supervisor_recommendations": plot_supervisor_recommendations_a(df),
                "rec_member_distribution": plot_rec_member_distribution_a(df),
                "certificate_status": plot_certificate_status_a(df),
                "submissions_over_time": plot_submissions_over_time_a(df),
                "review_by_risk_rating": plot_review_by_risk_rating_a(df),
                "top_applicants": plot_top_applicants_a(df),
                "certificate_received_percentage": plot_certificate_received_percentage_a(df),
                "review_recommendation_comparison": plot_review_recommendation_comparison_a(df),
                "plot_applications_vs_certificates": plot_applications_vs_certificates_a(df),
            })
        except Exception as e:
            print(f"Error generating charts for Form A: {e}")
            # Charts will be None if not generated, templates handle this gracefully

        return render_template("super_admin_form_a.html", role=role, forma=forma, **context)
    else:
        # Empty state with sample KPIs
        kpis = {
            'total_applications': 0,
            'this_month': 0,
            'growth_rate': 0,
            'certificates_issued': 0,
            'certificates_received': 0,
            'completion_rate': 0,
            'high_risk_count': 0
        }
        return render_template("super_admin_form_a.html", role=role, forma=forma, kpis=kpis)

### Form B Analytics with Professional Visualizations
from data_ploting import (plot_risk_rating_distribution_b,
plot_review_recommendations_b,
plot_supervisor_recommendations_b,
plot_rec_member_distribution_b,
plot_certificate_status_b,
plot_submissions_over_time_b,
plot_review_by_risk_rating_b,
plot_top_applicants_b,
plot_certificate_received_percentage_b,
plot_review_recommendation_comparison_b,
plot_applications_vs_certificates_b,
calculate_kpis_b,
create_sunburst_chart_b)

@app.route('/super_admin_form_b', methods=['GET', 'POST'])
def super_admin_form_b():
    user_id = session.get('id')
    if not user_id:
        return redirect(url_for('login_page'))
    user = db_session.query(User).filter(User.user_id==user_id).first()
    if not user:
        return redirect(url_for('login_page'))
    role = user.role.value

    formb = 'B'

    # Enhanced data collection with additional fields for better analytics
    forms_list = [
    {
        "id": form.form_id,
        "applicant_name": form.applicant_name,
        "submitted_at": form.submitted_at,
        "risk_rating": form.risk_level or 'Not Assessed',  # Map risk_level to risk_rating for consistency
        "supervisor": getattr(form, 'supervisor', None),
        "ethics_signature_date": form.supervisor_date,
        "supervisor_recommendation": form.recommendation,
        "first_reviewer_name": form.form_reviewed_by,
        "second_reviewer_name": form.form_reviewed_by1,
        "review_signature_date": form.review_signature_date,
        "review_recommendation": form.review_recommendation,
        "review_signature_date1": form.review_signature_date1,
        "review_recommendation1": form.review_recommendation1,
        "first_reviewer": form.reviewer_name1,
        "second_reviewer": form.reviewer_name2,
        "certificate_issued": form.certificate_issued,
        "certificate_received": form.certificate_received,
        "submitted_to_rec": form.submitted_to_rec if rec else False,
        "rec_full_name": rec.full_name if rec else None,
        "student_number": getattr(form, 'student_number', None),
        "department": getattr(form, 'department', None),
        "degree": getattr(form, 'degree', None)
    }
    for form, rec in (
        db_session.query(FormB, Rec)
        .outerjoin(Rec, FormB.form_id == Rec.form_id)
        .filter(FormB.submitted_at.isnot(None))  # Only include submitted forms
        .order_by(FormB.submitted_at.desc())
        .limit(200)  # Increased limit for better analytics
        .all()
    )
    ]
    
    # Debug log
    app.logger.info(f"Found {len(forms_list)} Form B submissions for analytics")
    
    if forms_list:
        df = pd.DataFrame(forms_list)
        
        # Calculate KPIs
        kpis = calculate_kpis_b(df)
        
        # Create enhanced visualizations with error handling
        context = {"kpis": kpis}
        
        try:
            context.update({
                # Interactive Plotly charts
                "sunburst_chart": create_sunburst_chart_b(df),
                "interactive_timeline": analytics.create_interactive_timeline(df, 'B'),
                "risk_analysis": analytics.create_advanced_risk_analysis(df, 'B'),
                "reviewer_performance": analytics.create_reviewer_performance_dashboard(df, 'B'),
                
                # Enhanced matplotlib charts
                "risk_rating_distribution": plot_risk_rating_distribution_b(df),
                "review_recommendations": plot_review_recommendations_b(df),
                "supervisor_recommendations": plot_supervisor_recommendations_b(df),
                "rec_member_distribution": plot_rec_member_distribution_b(df),
                "certificate_status": plot_certificate_status_b(df),
                "submissions_over_time": plot_submissions_over_time_b(df),
                "review_by_risk_rating": plot_review_by_risk_rating_b(df),
                "top_applicants": plot_top_applicants_b(df),
                "certificate_received_percentage": plot_certificate_received_percentage_b(df),
                "review_recommendation_comparison": plot_review_recommendation_comparison_b(df),
                "plot_applications_vs_certificates": plot_applications_vs_certificates_b(df),
            })
        except Exception as e:
            print(f"Error generating charts for Form B: {e}")
            # Charts will be None if not generated, templates handle this gracefully

        return render_template("super_admin_form_b.html", role=role, formb=formb, **context)
    else:
        # Empty state with sample KPIs
        kpis = {
            'total_applications': 0,
            'this_month': 0,
            'growth_rate': 0,
            'certificates_issued': 0,
            'certificates_received': 0,
            'completion_rate': 0,
            'high_risk_count': 0
        }
        return render_template("super_admin_form_b.html", role=role, formb=formb, kpis=kpis)
### Ploting form C

### Form C Analytics with Professional Visualizations  
from data_ploting import (plot_risk_rating_distribution_c,
plot_review_recommendations_c,
plot_supervisor_recommendations_c,
plot_rec_member_distribution_c,
plot_certificate_status_c,
plot_submissions_over_time_c,
plot_review_by_risk_rating_c,
plot_top_applicants_c,
plot_certificate_received_percentage_c,
plot_review_recommendation_comparison_c,
plot_applications_vs_certificates_c,
calculate_kpis_c,
create_sunburst_chart_c)

@app.route('/super_admin_form_c', methods=['GET', 'POST'])
def super_admin_form_c():
    user_id = session.get('id')
    if not user_id:
        return redirect(url_for('login_page'))
    user = db_session.query(User).filter(User.user_id==user_id).first()
    if not user:
        return redirect(url_for('login_page'))
    role = user.role.value

    formc = 'C'
    
    # Enhanced data collection with additional fields for better analytics
    forms_list = [
    {
        "id": form.form_id,
        "applicant_name": form.applicant_name,
        "submitted_at": form.submission_date,  # Use submission_date for Form C
        "risk_rating": form.risk_level or 'Not Assessed',  # Map risk_level to risk_rating for consistency
        "supervisor": getattr(form, 'supervisor', None),
        "ethics_signature_date": form.supervisor_date,
        "supervisor_recommendation": form.recommendation,
        "first_reviewer_name": form.form_reviewed_by,
        "second_reviewer_name": form.form_reviewed_by1,
        "review_signature_date": form.review_signature_date,
        "review_recommendation": form.review_recommendation,
        "review_signature_date1": form.review_signature_date1,
        "review_recommendation1": form.review_recommendation1,
        "first_reviewer": form.reviewer_name1,
        "second_reviewer": form.reviewer_name2,
        "certificate_issued": form.certificate_issued,
        "certificate_received": form.certificate_received,
        "submitted_to_rec": form.submitted_to_rec if rec else False,
        "rec_full_name": rec.full_name if rec else None,
        "student_number": getattr(form, 'student_number', None),
        "department": getattr(form, 'department', None),
        "degree": getattr(form, 'degree', None)
    }
    for form, rec in (
        db_session.query(FormC, Rec)
        .outerjoin(Rec, FormC.form_id == Rec.form_id)
        .filter(FormC.submission_date.isnot(None))  # Only include submitted forms
        .order_by(FormC.submission_date.desc())
        .limit(200)  # Increased limit for better analytics
        .all()
    )
    ]
    
    # Debug log
    app.logger.info(f"Found {len(forms_list)} Form C submissions for analytics")
    
    if forms_list:
        df = pd.DataFrame(forms_list)
        
        # Calculate KPIs
        kpis = calculate_kpis_c(df)
        
        # Create enhanced visualizations with error handling
        context = {"kpis": kpis}
        
        try:
            context.update({
                # Interactive Plotly charts
                "sunburst_chart": create_sunburst_chart_c(df),
                "interactive_timeline": analytics.create_interactive_timeline(df, 'C'),
                "risk_analysis": analytics.create_advanced_risk_analysis(df, 'C'),
                "reviewer_performance": analytics.create_reviewer_performance_dashboard(df, 'C'),
                
                # Enhanced matplotlib charts
                "risk_rating_distribution": plot_risk_rating_distribution_c(df),
                "review_recommendations": plot_review_recommendations_c(df),
                "supervisor_recommendations": plot_supervisor_recommendations_c(df),
                "rec_member_distribution": plot_rec_member_distribution_c(df),
                "certificate_status": plot_certificate_status_c(df),
                "submissions_over_time": plot_submissions_over_time_c(df),
                "review_by_risk_rating": plot_review_by_risk_rating_c(df),
                "top_applicants": plot_top_applicants_c(df),
                "certificate_received_percentage": plot_certificate_received_percentage_c(df),
                "review_recommendation_comparison": plot_review_recommendation_comparison_c(df),
                "plot_applications_vs_certificates": plot_applications_vs_certificates_c(df),
            })
        except Exception as e:
            print(f"Error generating charts for Form C: {e}")
            # Charts will be None if not generated, templates handle this gracefully

        return render_template("super_admin_form_c.html", role=role, formc=formc, **context)
    else:
        # Empty state with sample KPIs
        kpis = {
            'total_applications': 0,
            'this_month': 0,
            'growth_rate': 0,
            'certificates_issued': 0,
            'certificates_received': 0,
            'completion_rate': 0,
            'high_risk_count': 0
        }
        return render_template("super_admin_form_c.html", role=role, formc=formc, kpis=kpis)

# =====================================================================================================
# ADMIN/SUPERADMIN STATUS MONITORING PAGE
# =====================================================================================================
@app.route('/admin_status_monitor', methods=['GET'])
def admin_status_monitor():
    user_id = session.get('id')
    if not user_id:
        return redirect(url_for('login_page'))
    user = db_session.query(User).filter(User.user_id == user_id).first()
    if not user or user.role.value.lower() not in ['admin', 'super_admin']:
        return redirect(url_for('login_page'))
    role = user.role.value

    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    def normalize_datetime(dt_value):
        """Normalize DB datetimes so sorting and template math do not mix aware/naive values."""
        if not dt_value or not isinstance(dt_value, datetime):
            return dt_value
        return dt_value.astimezone(timezone.utc).replace(tzinfo=None) if dt_value.tzinfo else dt_value

    def apply_name_search(records, search_value):
        if not search_value:
            return records
        normalized_search = search_value.casefold()
        return [
            r for r in records
            if (r["applicant_name"] or "").casefold().find(normalized_search) != -1
        ]

    # Query FormA, FormB, FormC and combine
    def get_form_records(model, form_type):
        # Get the most recent form per user
        if hasattr(model, 'submitted_at'):
            latest_subq = (
                db_session.query(
                    model.user_id,
                    func.max(model.submitted_at).label("latest_date")
                )
                .group_by(model.user_id)
                .subquery()
            )
            query = db_session.query(model)
            query = query.join(latest_subq,
                (model.user_id == latest_subq.c.user_id) &
                (model.submitted_at == latest_subq.c.latest_date))
            results = query.order_by(model.submitted_at.desc()).all()
        elif hasattr(model, 'submission_date'):
            latest_subq = (
                db_session.query(
                    model.user_id,
                    func.max(model.submission_date).label("latest_date")
                )
                .group_by(model.user_id)
                .subquery()
            )
            query = db_session.query(model)
            query = query.join(latest_subq,
                (model.user_id == latest_subq.c.user_id) &
                (model.submission_date == latest_subq.c.latest_date))
            results = query.order_by(model.submission_date.desc()).all()
        else:
            query = db_session.query(model)
            results = query.all()
        records = []
        for form in results:
            rev1_name = None
            rev2_name = None
            if getattr(form, 'reviewer_name1', None):
                rev1_user = db_session.query(User).filter(User.user_id == form.reviewer_name1).first()
                rev1_name = rev1_user.full_name if rev1_user else form.reviewer_name1
            if getattr(form, 'reviewer_name2', None):
                rev2_user = db_session.query(User).filter(User.user_id == form.reviewer_name2).first()
                rev2_name = rev2_user.full_name if rev2_user else form.reviewer_name2

            rev1_data = {"date": None, "recommendation": None, "comments": None}
            rev2_data = {"date": None, "recommendation": None, "comments": None}

            slot0_reviewer = getattr(form, 'form_reviewed_by', None)
            slot1_reviewer = getattr(form, 'form_reviewed_by1', None)
            slot0_date = normalize_datetime(getattr(form, 'review_signature_date', None) or getattr(form, 'reviewer_date', None))
            slot1_date = normalize_datetime(getattr(form, 'review_signature_date1', None) or getattr(form, 'reviewer_date1', None))

            if slot0_reviewer == getattr(form, 'reviewer_name1', None):
                rev1_data["date"] = slot0_date
                rev1_data["recommendation"] = getattr(form, 'review_recommendation', None)
                rev1_data["comments"] = getattr(form, 'review_additional_comments', None)
            elif slot0_reviewer == getattr(form, 'reviewer_name2', None):
                rev2_data["date"] = slot0_date
                rev2_data["recommendation"] = getattr(form, 'review_recommendation', None)
                rev2_data["comments"] = getattr(form, 'review_additional_comments', None)

            if slot1_reviewer == getattr(form, 'reviewer_name1', None):
                rev1_data["date"] = slot1_date
                rev1_data["recommendation"] = getattr(form, 'review_recommendation1', None)
                rev1_data["comments"] = getattr(form, 'review_additional_comments1', None)
            elif slot1_reviewer == getattr(form, 'reviewer_name2', None):
                rev2_data["date"] = slot1_date
                rev2_data["recommendation"] = getattr(form, 'review_recommendation1', None)
                rev2_data["comments"] = getattr(form, 'review_additional_comments1', None)
            record = {
                "id": form.form_id,
                "form_type": form_type,
                "user_id":form.user_id,
                "applicant_name": getattr(form, 'applicant_name', None),
                "submitted_at": normalize_datetime(getattr(form, 'submitted_at', None) or getattr(form, 'submission_date', None)),
                "submitted": getattr(form, 'submitted', None),
                "risk_rating": getattr(form, 'risk_rating', None) or getattr(form, 'risk_level', None),
                "supervisor": getattr(form, 'supervisor', None) if hasattr(form, 'supervisor') else getattr(form, 'supervisor_name', None),
                "supervisor_date": normalize_datetime(getattr(form, 'supervisor_date', None)),
                "ethics_signature_date": normalize_datetime(getattr(form, 'ethics_signature_date', None)),
                "supervisor_recommendation": getattr(form, 'recommendation', None),
                "status": getattr(form, 'status', None),
                "first_reviewer_name": rev1_name,
                "second_reviewer_name": rev2_name,
                "first_reviewer": rev1_name,
                "second_reviewer": rev2_name,
                "signature_date": normalize_datetime(getattr(form, 'signature_date', None)),
                "recommendation": rev1_data["recommendation"],
                "first_reviewer_recommendation": rev1_data["recommendation"],
                "second_reviewer_recommendation": rev2_data["recommendation"],
                "first_reviewer_date": rev1_data["date"],
                "second_reviewer_date": rev2_data["date"],
                "first_reviewer_comment": rev1_data["comments"],
                "second_reviewer_comment": rev2_data["comments"],
                "certificate_issued": getattr(form, 'certificate_issued', None) if getattr(form, 'certificate_issued', None) is not None else 'Not Issued',
                "certificate_received": normalize_datetime(getattr(form, 'certificate_received', None)),
                "submitted_to_reviewers": getattr(form, 'submitted_to_reviewers', None),
                "submitted_to_rec": getattr(form, 'submitted_to_rec', None),
                "rec_status": getattr(form, 'rec_status', None),
                "rejected_or_accepted": getattr(form, 'rejected_or_accepted', None),
                "form_supervisor_status": getattr(form, 'form_supervisor_status', None),
                "ethics_form_status": getattr(form, 'ethics_form_status', None),
                "form_review_comment": getattr(form, 'form_review_comment', None),
                "form_review_comment1": getattr(form, 'form_review_comment1', None),
            }
            records.append(record)
        return records

    all_records = []
    for model, ftype in [(FormA, 'FORM A'), (FormB, 'FORM B'), (FormC, 'FORM C')]:
        all_records.extend(get_form_records(model, ftype))

    name_suggestions = sorted({
        record["applicant_name"]
        for record in all_records
        if record["applicant_name"]
    }, key=lambda name: name.casefold())
    filtered_records = apply_name_search(all_records, search_query)
    filtered_records.sort(
        key=lambda item: item["submitted_at"] or datetime.min,
        reverse=True
    )

    total = len(filtered_records)
    start_idx = max((page - 1) * per_page, 0)
    end_idx = start_idx + per_page
    forms_list = filtered_records[start_idx:end_idx]
    current = datetime.utcnow()
    return render_template(
        'admin_status_monitor.html',
        role=role,
        current_time=current,
        forms_list=forms_list,
        page=page,
        per_page=per_page,
        total=total,
        search_query=search_query,
        name_suggestions=name_suggestions
    )

@app.route('/super_admin_monitoring_page_a',methods=['GET','POST'])
def super_admin_monitoring_page_a():
    user_id = session.get('id')
    if not user_id:
        return redirect(url_for('login_page'))
    user=db_session.query(User).filter(User.user_id==user_id).first()
    if not user:
        return redirect(url_for('login_page'))
    role=user.role.value

    # Step 1: Subquery to get the latest submitted_at per student
    latest_subq = (
        db_session.query(
            FormA.user_id,
            func.max(FormA.submitted_at).label("latest_date")
        )
        .group_by(FormA.user_id)
        .subquery()
    )
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20
    base_query = (
        db_session.query(FormA, Rec)
        .join(latest_subq,
              (FormA.user_id == latest_subq.c.user_id) &
              (FormA.submitted_at == latest_subq.c.latest_date))
        .outerjoin(Rec, FormA.form_id == Rec.form_id)
        .order_by(FormA.user_id, FormA.submitted_at.desc())
    )
    results = base_query.offset((page-1)*per_page).limit(per_page).all()
    total = base_query.count()

   
    # Step 3: Merge REC names into one form entry
    forms_dict = {}
    for form, rec in results:
        # Resolve First Reviewer Info
        first_reviewer_user = db_session.query(User).filter(User.user_id == form.reviewer_name1).first()
        second_reviewer_user = db_session.query(User).filter(User.user_id == form.reviewer_name2).first()
        
        # Correctly attribute feedback regardless of slot order in DB
        rev1_data = {"name": first_reviewer_user.full_name if first_reviewer_user else None, "date": None, "recommendation": None}
        rev2_data = {"name": second_reviewer_user.full_name if second_reviewer_user else None, "date": None, "recommendation": None}
        
        # Check Slot 0
        if form.form_reviewed_by == form.reviewer_name1:
            rev1_data["date"] = form.review_signature_date
            rev1_data["recommendation"] = form.review_recommendation
        elif form.form_reviewed_by == form.reviewer_name2:
            rev2_data["date"] = form.review_signature_date
            rev2_data["recommendation"] = form.review_recommendation
            
        # Check Slot 1
        if form.form_reviewed_by1 == form.reviewer_name1:
            rev1_data["date"] = form.review_signature_date1
            rev1_data["recommendation"] = form.review_recommendation1
        elif form.form_reviewed_by1 == form.reviewer_name2:
            rev2_data["date"] = form.review_signature_date1
            rev2_data["recommendation"] = form.review_recommendation1

        if form.form_id not in forms_dict:
            # Create the base form entry
            forms_dict[form.form_id] = {
                "id": form.form_id,
                "applicant_name": form.applicant_name,
                "submitted_at": form.submitted_at,
                "risk_rating": form.risk_rating,
                "supervisor": form.supervisor,
                "supervisor_date": form.supervisor_date,
                "ethics_signature_date": form.ethics_signature_date,
                "supervisor_recommendation": form.recommendation,
                "first_reviewer_name": rev1_data["name"],
                "first_reviewer_date": rev1_data["date"],
                "first_reviewer_recommendation": rev1_data["recommendation"],
                "second_reviewer_name": rev2_data["name"],
                "second_reviewer_date": rev2_data["date"],
                "first_reviewer": form.reviewer_name1,
                "second_reviewer": form.reviewer_name2,
                "signature_date": form.signature_date,
                "recommendation": form.review_recommendation,
                "status": form.status,
                "second_reviewer_recommendation": rev2_data["recommendation"],
                "certificate_issued": form.certificate_issued if form.certificate_issued is not None else 'Not Issued',
                "certificate_received": form.certificate_received,
                "submitted_to_reviewers": form.submitted_to_reviewers,
                "submitted_to_rec": form.submitted_to_rec,
                "rec_status": form.rec_status,
                "rejected_or_accepted": form.rejected_or_accepted,
                "form_supervisor_status": form.form_supervisor_status,
                "ethics_form_status": form.ethics_form_status,
                "form_review_comment": form.form_review_comment,
                "form_review_comment1": form.form_review_comment1,
                "rec_full_names": []  # Store list of REC full names
            }
        # Add REC name if available
        if rec and rec.full_name and rec.full_name not in forms_dict[form.form_id]["rec_full_names"]:
            forms_dict[form.form_id]["rec_full_names"].append(rec.full_name)

    # Step 4: Convert to list for output
    forms_list = list(forms_dict.values())
    current = datetime.now(timezone.utc)
    return render_template('super_admin_monitoring_page_a.html',role=role,current_time=current, forms_list=forms_list, page=page, per_page=per_page, total=total)


@app.route('/super_admin_monitoring_page_b',methods=['GET','POST'])
def super_admin_monitoring_page_b():
    user_id = session.get('id')
    if not user_id:
        return redirect(url_for('login_page'))
    user=db_session.query(User).filter(User.user_id==user_id).first()
    if not user:
        return redirect(url_for('login_page'))
    role=user.role.value
    # Step 1: Subquery to get the latest submitted_at per student
    latest_subq = (
        db_session.query(
            FormB.user_id,
            func.max(FormB.submitted_at).label("latest_date")
        )
        .group_by(FormB.user_id)
        .subquery()
    )
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20
    base_query = (
        db_session.query(FormB, Rec)
        .options(
            defer(FormB.permission_letter),
            defer(FormB.prior_clearance),
            defer(FormB.ethics_evidence),
            defer(FormB.proposal_path),
            defer(FormB.pending_note),
            defer(FormB.private_permission_file)
        )
        .join(latest_subq,
              (FormB.user_id == latest_subq.c.user_id) &
              (FormB.submitted_at == latest_subq.c.latest_date))
        .outerjoin(Rec, FormB.form_id == Rec.form_id)
        .order_by(FormB.user_id, FormB.submitted_at.desc())
    )
    results = base_query.offset((page-1)*per_page).limit(per_page).all()
    total = base_query.count()

   
    # Step 3: Merge REC names into one form entry
    forms_dict = {}
    for form, rec in results:
        # Resolve First Reviewer Info
        first_reviewer_user = db_session.query(User).filter(User.user_id == form.reviewer_name1).first()
        second_reviewer_user = db_session.query(User).filter(User.user_id == form.reviewer_name2).first()
        
        # Correctly attribute feedback regardless of slot order in DB
        rev1_data = {"name": first_reviewer_user.full_name if first_reviewer_user else None, "date": None, "recommendation": None}
        rev2_data = {"name": second_reviewer_user.full_name if second_reviewer_user else None, "date": None, "recommendation": None}
        
        # Check Slot 0
        if form.form_reviewed_by == form.reviewer_name1:
            rev1_data["date"] = form.review_signature_date
            rev1_data["recommendation"] = form.review_recommendation
        elif form.form_reviewed_by == form.reviewer_name2:
            rev2_data["date"] = form.review_signature_date
            rev2_data["recommendation"] = form.review_recommendation
            
        # Check Slot 1
        if form.form_reviewed_by1 == form.reviewer_name1:
            rev1_data["date"] = form.review_signature_date1
            rev1_data["recommendation"] = form.review_recommendation1
        elif form.form_reviewed_by1 == form.reviewer_name2:
            rev2_data["date"] = form.review_signature_date1
            rev2_data["recommendation"] = form.review_recommendation1

        if form.form_id not in forms_dict:
            # Create the base form entry
            forms_dict[form.form_id] = {
                "id": form.form_id,
                "applicant_name": form.applicant_name,
                "submitted_at": form.submitted_at,
                "risk_rating": form.risk_level,
                "supervisor": form.supervisor,
                "supervisor_date": form.supervisor_date,
                "ethics_signature_date": form.ethics_signature_date,
                "supervisor_recommendation": form.recommendation,
                "first_reviewer": form.reviewer_name1,
                "second_reviewer": form.reviewer_name2,
                "signature_date": form.signature_date,
                "recommendation": form.review_recommendation,
                "status": form.status,
                "first_reviewer_name": rev1_data["name"],
                "first_reviewer_date": rev1_data["date"],
                "first_reviewer_recommendation": rev1_data["recommendation"],
                "second_reviewer_name": rev2_data["name"],
                "second_reviewer_date": rev2_data["date"],
                "second_reviewer_recommendation": rev2_data["recommendation"],
                "certificate_issued": form.certificate_issued if form.certificate_issued is not None else 'Not Issued',
                "certificate_received": form.certificate_received,
                "submitted_to_reviewers": form.submitted_to_reviewers,
                "submitted_to_rec": form.submitted_to_rec,
                "rec_status": form.rec_status,
                "rejected_or_accepted": form.rejected_or_accepted,
                "form_supervisor_status": form.form_supervisor_status,
                "ethics_form_status": form.ethics_form_status,
                "form_review_comment": form.form_review_comment,
                "form_review_comment1": form.form_review_comment1,
                "rec_full_names": []  # Store list of REC full names
            }
        # Add REC name if available
        if rec and rec.full_name and rec.full_name not in forms_dict[form.form_id]["rec_full_names"]:
            forms_dict[form.form_id]["rec_full_names"].append(rec.full_name)

    # Step 4: Convert to list for output
    forms_list = list(forms_dict.values())
    current = datetime.now(timezone.utc)
    return render_template('super_admin_monitoring_page_b.html',role=role,current_time=current, forms_list=forms_list, page=page, per_page=per_page, total=total)




@app.route('/super_admin_monitoring_page_c',methods=['GET','POST'])
def super_admin_monitoring_page_c():
    user_id=session.get('id')
    user=db_session.query(User).filter(User.user_id==user_id).first()
    role=user.role.value
    # Step 1: Subquery to get the latest submitted_at per student
    latest_subq = (
        db_session.query(
            FormC.user_id,
            func.max(FormC.submission_date).label("latest_date")
        )
        .group_by(FormC.user_id)
        .subquery()
    )
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20
    base_query = (
        db_session.query(FormC, Rec)
        .join(latest_subq,
              (FormC.user_id == latest_subq.c.user_id) &
              (FormC.submission_date == latest_subq.c.latest_date))
        .outerjoin(Rec, FormC.form_id == Rec.form_id)
        .order_by(FormC.user_id, FormC.submission_date.desc())
    )
    results = base_query.offset((page-1)*per_page).limit(per_page).all()
    total = base_query.count()

   
    # Step 3: Merge REC names into one form entry
    forms_dict = {}
    for form, rec in results:
        # Resolve First Reviewer Info
        first_reviewer_user = db_session.query(User).filter(User.user_id == form.reviewer_name1).first()
        second_reviewer_user = db_session.query(User).filter(User.user_id == form.reviewer_name2).first()
        
        # Correctly attribute feedback regardless of slot order in DB
        rev1_data = {"name": first_reviewer_user.full_name if first_reviewer_user else None, "date": None, "recommendation": None}
        rev2_data = {"name": second_reviewer_user.full_name if second_reviewer_user else None, "date": None, "recommendation": None}
        
        # Check Slot 0
        if form.form_reviewed_by == form.reviewer_name1:
            rev1_data["date"] = form.review_signature_date
            rev1_data["recommendation"] = form.review_recommendation
        elif form.form_reviewed_by == form.reviewer_name2:
            rev2_data["date"] = form.review_signature_date
            rev2_data["recommendation"] = form.review_recommendation
            
        # Check Slot 1
        if form.form_reviewed_by1 == form.reviewer_name1:
            rev1_data["date"] = form.review_signature_date1
            rev1_data["recommendation"] = form.review_recommendation1
        elif form.form_reviewed_by1 == form.reviewer_name2:
            rev2_data["date"] = form.review_signature_date1
            rev2_data["recommendation"] = form.review_recommendation1

        if form.form_id not in forms_dict:
            # Create the base form entry
            forms_dict[form.form_id] = {
                "id": form.form_id,
                "applicant_name": form.applicant_name,
                "submission_date": form.submission_date,
                "risk_level": form.risk_level,
                "supervisor_name": form.supervisor_name,
                "supervisor_date": form.supervisor_date,
                "ethics_signature_date": form.ethics_signature_date,
                "supervisor_recommendation": form.recommendation,
                "first_reviewer": form.reviewer_name1,
                "second_reviewer": form.reviewer_name2,
                "signature_date": form.signature_date,
                "recommendation": form.review_recommendation,
                "status": form.status,
                "first_reviewer_name": rev1_data["name"],
                "first_reviewer_date": rev1_data["date"],
                "first_reviewer_recommendation": rev1_data["recommendation"],
                "second_reviewer_name": rev2_data["name"],
                "second_reviewer_date": rev2_data["date"],
                "second_reviewer_recommendation": rev2_data["recommendation"],
                "certificate_issued": form.certificate_issued if form.certificate_issued is not None else 'Not Issued',
                "certificate_received": form.certificate_received,
                "submitted_to_reviewers": form.submitted_to_reviewers,
                "submitted_to_rec": form.submitted_to_rec,
                "rec_status": form.rec_status,
                "rejected_or_accepted": form.rejected_or_accepted,
                "form_supervisor_status": form.form_supervisor_status,
                "ethics_form_status": form.ethics_form_status,
                "form_review_comment": form.form_review_comment,
                "form_review_comment1": form.form_review_comment1,
                "rec_full_names": []  # Store list of REC full names
            }
        # Add REC name if available
        if rec and rec.full_name and rec.full_name not in forms_dict[form.form_id]["rec_full_names"]:
            forms_dict[form.form_id]["rec_full_names"].append(rec.full_name)

    # Step 4: Convert to list for output
    forms_list = list(forms_dict.values())
    current = datetime.now(timezone.utc)
    return render_template('super_admin_monitoring_page_c.html',role=role,current_time=current, forms_list=forms_list, page=page, per_page=per_page, total=total)





@app.route('/delete_user/<string:id>', methods=['GET','POST'])
@role_required('ADMIN', 'SUPER_ADMIN')
def delete_user(id):
    if request.method != 'POST':
        flash("Use the delete button to remove a user.", "warning")
        return redirect(url_for('all_users'))

    try:
        user_to_delete = db_session.query(User).filter_by(user_id=id).first()
        admin_id = session.get('id')
        if user_to_delete:
            deleted_user_label = user_to_delete.email or user_to_delete.full_name or id

            # Remove dependent rows first to avoid FK constraint failures.
            db_session.query(LoginLog).filter_by(user_id=id).delete(synchronize_session=False)
            db_session.query(UserActivityLog).filter(
                or_(
                    UserActivityLog.user_id == id,
                    UserActivityLog.target_user_id == id
                )
            ).delete(synchronize_session=False)
            db_session.query(FormARequirements).filter_by(user_id=id).delete(synchronize_session=False)
            db_session.query(FormA).filter_by(user_id=id).delete(synchronize_session=False)
            db_session.query(FormB).filter_by(user_id=id).delete(synchronize_session=False)
            db_session.query(FormC).filter_by(user_id=id).delete(synchronize_session=False)

            # Use bulk delete for User to avoid ORM relationship synchronization
            # that can attempt to set child FKs to NULL (logs.user_id is NOT NULL).
            db_session.query(User).filter_by(user_id=id).delete(synchronize_session=False)
            # Log admin action
            if admin_id:
                db_session.add(UserActivityLog(
                    user_id=admin_id,
                    action='admin_delete_user',
                    page=request.path,
                    timestamp=datetime.now(),
                    details=f"Admin deleted user with user_id: {id} ({deleted_user_label})"
                ))
            db_session.commit()
            flash("User deleted successfully", "success")
            return redirect(url_for('all_users'))
        else:
            flash("User not found", "warning")
            return redirect(url_for('all_users'))

    except Exception as e:
        db_session.rollback()  # rollback to recover from DB error
        app.logger.exception("Delete user error for user_id=%s", id)
        flash("An error occurred while deleting the user. Check server logs for details.", "danger")
        return redirect(url_for('all_users'))


@app.route('/all_users', methods=['GET', 'POST'])
@role_required('ADMIN', 'SUPER_ADMIN')
def all_users():
    user_id=session.get('id')
    user_profile=db_session.query(User).filter_by(user_id=user_id).first()
    
    # If user_profile is None, redirect to login
    if not user_profile:
        flash("Session expired. Please login again.")
        return redirect(url_for('login_page'))
    
    # Pagination logic
    page = request.args.get('page', 1, type=int)
    per_page = 20
    users_query = db_session.query(User)
    search_query = (request.args.get('search') or '').strip()
    auth_status = (request.args.get('auth_status') or '').strip().lower()

    if search_query:
        search_term = f"%{search_query}%"
        users_query = users_query.filter(
            or_(
                User.full_name.ilike(search_term),
                User.email.ilike(search_term),
                User.role.cast(String).ilike(search_term)
            )
        )

    if auth_status == 'authenticated':
        users_query = users_query.filter(
            func.lower(func.coalesce(cast(User.authenticate_student, String), 'false')).in_(['true', '1'])
        )
    elif auth_status == 'not_authenticated':
        users_query = users_query.filter(
            func.lower(func.coalesce(cast(User.authenticate_student, String), 'false')).in_(['false', '0', 'none', ''])
        )

    total_users = users_query.count()
    all_users = users_query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total_users + per_page - 1) // per_page
    role = user_profile.role.value

    # Backward-compatible fallback for legacy redirects using ?messages=...
    query_messages = []
    query_msg = request.args.get('messages')
    if query_msg:
        query_messages.append(query_msg)

    return render_template(
        "user-list.html",
        role=role,
        user_profile=user_profile,
        all_users=all_users,
        messages=query_messages,
        search_query=search_query,
        auth_status=auth_status,
        page=page,
        total_pages=total_pages,
    )
@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    email = data.get('email')
    if not email:
        return jsonify({'message': 'Email is required'}), 400

    user = db_session.query(User).filter_by(email=email).first()
    if not user:
        # For security, don't reveal if the email exists
        return jsonify({'message': 'If that email exists, a reset link has been sent.'}), 200

    # Generate token and expiry
    token = generate_reset_token()
    user.reset_token = token
    user.reset_token_expiry = datetime.now(timezone.utc) + timedelta(minutes=15)
    session.commit()

    # Send email to user with the token
    try:
        send_email("motsietsepang@gmail.com", "UJ Ethics System: Password Resset", token)
    except:
        print("Error in ['/api/forgot-password'] ", "password reset token email sending failed.")
        return jsonify({'message': 'Server failed to send email. Contact admin.'}), 500

    return jsonify({'message': 'If that email exists, a reset code has been sent.'}), 200



@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('new_password')

    if not token or not new_password:
        return jsonify({'message': 'Token and new password are required'}), 400

    user = session.query(User).filter_by(reset_token=token).first()
    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.now(timezone.utc):
        return jsonify({'message': 'Invalid or expired token'}), 400
    
    is_valid, message = validate_password(new_password)
    if not is_valid:
        return jsonify({'message': message}), 400

    # Update password
    user.password = new_password
    user.reset_token = None
    user.reset_token_expiry = None
    session.commit()

    return jsonify({'message': 'Password has been reset successfully.'}), 200

@app.route('/api/supervisors', methods=['GET'])
def get_supervisors():
    supervisors = db_session.query(User).filter(User.role == UserRole.SUPERVISOR.value).all()
    try:
        # Convert to list of dicts
        result = [
            {
                "user_id": sup.user_id,
                "full_name": sup.full_name,
                "email": sup.email
            }
            for sup in supervisors
        ]
        
        return jsonify(result), 200
    except Exception as e:
            print("Error fetching supervisors:", str(e))  # visible in Render logs
            return jsonify({"error": "Failed to fetch supervisors"}), 500


@app.route('/ethics_pack', methods=['GET'])
def ethics_pack():
    try:
        user_id = session.get('id')
        if not user_id:
            return redirect(url_for('login_page'))

        watched_video = db_session.query(Watched).filter_by(user_id=user_id).first()

        if watched_video is None:
            watched_video = Watched(user_id=user_id, watched=True)
            db_session.add(watched_video)
            db_session.commit()

        return render_template('ethics_pack.html')

    except Exception as e:
        db_session.rollback()
        print("Error in /ethics_pack:", str(e))
        msg = "An error occurred while loading the ethics pack."
        return render_template('ethics_pack.html', messages=[msg])



@app.route('/dashboard', methods=['GET'])
def dashboard ():
    user_id = session.get('id')
    if not user_id:
        return redirect(url_for('login_page'))
    
    # Get form submission info
    form_a = db_session.query(FormA).filter_by(user_id=user_id).first()
    date_str = ''
    if form_a:
        date = form_a.submitted_at
        date_str = date.strftime('%Y-%m-%d')
    
    # Check if student has FormARequirements and if files still exist
    form_requirements = db_session.query(FormARequirements).filter_by(user_id=user_id).first()
    files_missing = False
    missing_files_info = {}
    
    if form_requirements:
        # Check if uploaded files still exist on the filesystem
        upload_folder = get_upload_folder()
        file_fields = [
            ('permission_letter', 'Permission Letters'),
            ('research_tools_path', 'Research Tools'),
            ('proposal_path', 'Research Proposal'),
            ('impact_assessment_path', 'Impact Assessment'),
            ('prior_clearance', 'Prior Clearance'),
            ('ethics_evidence_path', 'Ethics Evidence'),
            ('participation_info_sheet', 'Participant Info Sheet'),
            ('pending_note', 'Pending Note')
        ]
        
        for field_name, display_name in file_fields:
            file_data = getattr(form_requirements, field_name)
            if file_data:
                # If it's bytes or memoryview, it's a blob and definitely exists
                if isinstance(file_data, (bytes, memoryview)):
                    continue
                    
                # If it's a string, it's a legacy path, check if it exists on disk
                if isinstance(file_data, str):
                    if file_data.startswith('uploads/form/'):
                        clean_path = file_data.replace('uploads/form/', '')
                    elif file_data.startswith('form/'):
                        clean_path = file_data.replace('form/', '')
                    else:
                        clean_path = file_data
                    
                    full_path = os.path.join(upload_folder, clean_path)
                    if not os.path.exists(full_path):
                        files_missing = True
                        missing_files_info[field_name] = {
                            'display_name': display_name,
                            'original_path': file_data
                        }
    
    return render_template('dashboard.html', 
                         date=date_str, 
                         form_requirements=form_requirements,
                         files_missing=files_missing,
                         missing_files_info=missing_files_info)



# =====================================================================================================
# THIS SECTION IS FOR HANDLING FORMS
# =====================================================================================================

# FORM A =====================================================================================================

@app.route('/submit_form_a_requirements', methods=['GET', 'POST'])
def submit_form_a_requirements():

    # Get user ID
    user_id = session.get('id')
    if not user_id:
        return redirect(url_for('login_page'))
    
    form = db_session.query(FormARequirements).filter_by(user_id=user_id).first()

    if request.method == 'POST':
        try:
            UPLOAD_FOLDER = get_upload_folder()
            # Ensure upload directory exists before saving any files
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)

            # Get form data
            needs_permission = request.form.get('need_permission') == 'Yes'
            has_clearance = request.form.get('has_clearance') == 'Yes'
            company_requires_jbs = request.form.get('company_requires_jbs') == 'Yes'

            

            # Restrict if user already submitted Form B or C
            if db_session.query(FormB).options(
                defer(FormB.permission_letter),
                defer(FormB.prior_clearance),
                defer(FormB.ethics_evidence),
                defer(FormB.proposal_path),
                defer(FormB.pending_note),
                defer(FormB.private_permission_file)
            ).filter_by(user_id=user_id).first() or \
               db_session.query(FormC).filter_by(user_id=user_id).first():
                flash("You are not permitted to fill this form", "warning")
                return redirect(url_for("student_dashboard"))
            formA=db_session.query(FormA).filter_by(user_id=user_id).first()
            
            # Handle permission letters (multiple files)
            permission_letter_data = None
            permission_letter_fname = None
            pending_note_data = None
            pending_note_fname = None
            
            needs_permission = request.form.get('need_permission')
            if needs_permission == 'Yes':
                uploaded_files = request.files.getlist('permission_letter[]')
                valid_files = [f for f in uploaded_files if f and f.filename != '']
                
                if len(valid_files) > 1:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zf:
                        for f in valid_files:
                            zf.writestr(secure_filename(f.filename), f.read())
                    permission_letter_data = zip_buffer.getvalue()
                    permission_letter_fname = "permission_letters.zip"
                    needs_permission = True
                elif len(valid_files) == 1:
                    permission_letter_data, permission_letter_fname = read_file_blob(valid_files[0])
                    needs_permission = True
            else:
                if needs_permission == 'No':
                    needs_permission = False
                elif needs_permission == "Pending":
                    needs_permission = None
                    pending_note_data, pending_note_fname = read_file_blob(request.files.get('pending_note'))
            
            # Handle other file uploads (single files)
            research_tools_data, research_tools_fname = read_file_blob(request.files.get('research_tools_path'))
            prior_clearance_data, prior_clearance_fname = read_file_blob(request.files.get('prior_clearance')) if has_clearance else (None, None)
            prior_clearance1_data, prior_clearance1_fname = read_file_blob(request.files.get('prior_clearance1')) if company_requires_jbs else (None, None)
            proposal_data, proposal_fname = read_file_blob(request.files.get('proposal_path'))
            impact_data, impact_fname = read_file_blob(request.files.get('impact_assessment_path'))
            participation_data, participation_fname = read_file_blob(request.files.get('participation_info_sheet'))


            # Save or update DB record
            form = db_session.query(FormARequirements).filter_by(user_id=user_id).first()

            # Validate required/conditional uploads using incoming files OR existing stored values
            missing_files = []

            def has_file(new_data, existing_data):
                return bool(new_data) or bool(existing_data)

            if not has_file(research_tools_data, form.research_tools_path if form else None):
                missing_files.append('Survey / Questionnaire / Focus Group Questions')
            if not has_file(proposal_data, form.proposal_path if form else None):
                missing_files.append('Research Proposal')
            if not has_file(impact_data, form.impact_assessment_path if form else None):
                missing_files.append('Personal Impact Assessment Form')
            if not has_file(participation_data, form.participation_info_sheet if form else None):
                missing_files.append('Participation Information Sheet & Consent Form')

            if needs_permission is True and not has_file(permission_letter_data, form.permission_letter if form else None):
                missing_files.append('Company Permission Letter')
            if needs_permission is None and not has_file(pending_note_data, form.pending_note if form else None):
                missing_files.append('Pending Note')
            if has_clearance and not has_file(prior_clearance_data, form.prior_clearance if form else None):
                missing_files.append('Prior Ethical Clearance Document')
            if company_requires_jbs and not has_file(prior_clearance1_data, form.prior_clearance1 if form else None):
                missing_files.append('JBS Ethical Clearance Document')

            if missing_files:
                flash('Missing required upload(s): ' + ', '.join(missing_files), 'danger')
                return redirect(url_for('submit_form_a_requirements'))
            
            if form:
                form.needs_permission = needs_permission
                form.has_clearance = has_clearance
                form.company_requires_jbs = company_requires_jbs
                form.form_type = "FORM A"
                
                if permission_letter_data:
                    form.permission_letter = permission_letter_data
                    form.permission_letter_filename = permission_letter_fname
                
                if research_tools_data:
                    form.research_tools_path = research_tools_data
                    form.research_tools_filename = research_tools_fname
                    
                if prior_clearance_data:
                    form.prior_clearance = prior_clearance_data
                    form.prior_clearance_filename = prior_clearance_fname
                    
                if prior_clearance1_data:
                    form.prior_clearance1 = prior_clearance1_data
                    form.prior_clearance1_filename = prior_clearance1_fname
                    
                if proposal_data:
                    form.proposal_path = proposal_data
                    form.proposal_filename = proposal_fname
                    
                if pending_note_data:
                    form.pending_note = pending_note_data
                    form.pending_note_filename = pending_note_fname
                    
                if impact_data:
                    form.impact_assessment_path = impact_data
                    form.impact_assessment_filename = impact_fname
                    
                if participation_data:
                    form.participation_info_sheet = participation_data
                    form.participation_info_filename = participation_fname
                
                db_session.add(form)
                db_session.commit()
                if form and not formA:
                    return redirect(url_for('form_a_sec1'))
                else:
                    return redirect(url_for('student_dashboard'))
                
            else:
                form = FormARequirements(
                    user_id=user_id,
                    form_type="FORM A",
                    needs_permission=needs_permission,
                    permission_letter=permission_letter_data,
                    permission_letter_filename=permission_letter_fname,
                    has_clearance=has_clearance,
                    pending_note=pending_note_data,
                    pending_note_filename=pending_note_fname,
                    company_requires_jbs=company_requires_jbs,
                    research_tools_path=research_tools_data,
                    research_tools_filename=research_tools_fname,
                    proposal_path=proposal_data,
                    proposal_filename=proposal_fname,
                    impact_assessment_path=impact_data,
                    impact_assessment_filename=impact_fname,
                    prior_clearance=prior_clearance_data,
                    prior_clearance_filename=prior_clearance_fname,
                    prior_clearance1=prior_clearance1_data,
                    prior_clearance1_filename=prior_clearance1_fname,
                    participation_info_sheet=participation_data,
                    participation_info_filename=participation_fname
                )
                db_session.add(form)
                db_session.commit()

                # New form flow continues to section 1 as before
                return redirect(url_for('form_a_sec1'))

        except Exception as e:
            db_session.rollback()
            return jsonify({'error': str(e)}), 500

    return render_template('form-a-upload.html',from_dashboard=form)

@app.route('/submit_form_c_requirements', methods=['GET', 'POST'])
def submit_form_c_requirements():


    # Get user ID from session (adjust based on your auth system)
    user_id = session.get('id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
            
    
    # Check if form exists for this user
    form = db_session.query(FormARequirements).filter_by(user_id=user_id).first()
    if request.method=='POST':
        try:
            UPLOAD_FOLDER = get_upload_folder()
            

            formB = db_session.query(FormB).filter_by(user_id=user_id).first()
            if formB:
                flash("You are not permitted to fill this form", "warning")
                return redirect(url_for("student_dashboard"))
                
            formA = db_session.query(FormA).filter_by(user_id=user_id).first()
            if formA:
                flash("You are not permitted to fill this form", "warning")
                return redirect(url_for("student_dashboard"))

            formC = db_session.query(FormC).filter_by(user_id=user_id).first()
            
            # Save files based on form field names (corrected from request.form to request.files)
            proposal_data, proposal_filename = read_file_blob('proposal')
          
            # Validate required files
            if not proposal_data:
                return jsonify({'error': 'Missing required files'}), 400
                
            
         
            if form:
                # Update existing form
                form.user_id=user_id
                form.form_type="FORM C"
                form.updated_at=datetime.now()
                
                if proposal_data:
                    form.files = proposal_data
                    form.files_filename = proposal_filename

                db_session.add(form)
                db_session.commit()
                if form and not formC:
                    return redirect(url_for('form_c_sec1'))
                else:
                    return redirect(url_for('student_dashboard'))
                
            else:
                # Create new record
                form = FormARequirements(
                    user_id=user_id,
                    form_type="FORM C",
                    updated_at=datetime.now(),
                    files = proposal_data,
                    files_filename = proposal_filename
                )
            
                db_session.add(form)
                db_session.commit()
            
                return redirect(url_for('form_c_sec1'))
            
        except Exception as e:
            db_session.rollback()
            return jsonify({'error': str(e)}), 500
  
    return render_template('form-c-upload.html',from_dashboard=form)


@app.route('/submit_form_b_requirements', methods=['GET', 'POST'])
def submit_form_b_requirements():
    # Get user ID from session
    user_id = session.get('id')
    if not user_id:
        return redirect(url_for('login_page'))
        
    # Check if form exists for this user
    form = db_session.query(FormARequirements).filter_by(user_id=user_id).first()

    if request.method == 'POST':
        try:
            # Basic status flags
            needs_permission_val = request.form.get('need_permission')
            has_clearance = request.form.get('has_clearance') == 'Yes'
            # Note: has_ethics_evidence might not be in Form B template, but let's be safe
            has_ethics_evidence = request.form.get('has_ethics_evidence') == 'Yes'
            
            # Check for conflict with other forms
            formA = db_session.query(FormA).filter_by(user_id=user_id).first()
            if formA:
                flash("You are not permitted to fill this form", "warning")
                return redirect(url_for("student_dashboard"))
                
            formC = db_session.query(FormC).filter_by(user_id=user_id).first()
            if formC:
                flash("You are not permitted to fill this form", "warning")
                return redirect(url_for("student_dashboard"))
            
            formB = db_session.query(FormB).options(
                defer(FormB.permission_letter),
                defer(FormB.prior_clearance),
                defer(FormB.ethics_evidence),
                defer(FormB.proposal_path),
                defer(FormB.pending_note),
                defer(FormB.private_permission_file)
            ).filter_by(user_id=user_id).first()

            # Handle permission letters (multiple files possible)
            permission_letter_data = None
            permission_letter_fname = None
            
            if needs_permission_val == 'Yes':
                uploaded_files = request.files.getlist('permission_letter_path[]')
                valid_files = [f for f in uploaded_files if f and f.filename != '']
                
                if len(valid_files) > 1:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zf:
                        for f in valid_files:
                            zf.writestr(secure_filename(f.filename), f.read())
                    permission_letter_data = zip_buffer.getvalue()
                    permission_letter_fname = "permission_letters.zip"
                elif len(valid_files) == 1:
                    permission_letter_data, permission_letter_fname = read_file_blob(valid_files[0])
            
            # Convert needs_permission to boolean/None for storage
            needs_permission_bool = None
            if needs_permission_val == 'Yes':
                needs_permission_bool = True
            elif needs_permission_val == 'No':
                needs_permission_bool = False
            # 'Pending' leaves it as None
            
            # Handle other files
            prior_clearance_data, prior_clearance_fname = read_file_blob('prior_clearance_path') if has_clearance else (None, None)
            ethics_evidence_data, ethics_evidence_fname = read_file_blob('ethics_evidence') if has_ethics_evidence else (None, None)
            proposal_data, proposal_fname = read_file_blob('proposal_path')
            pending_note_data, pending_note_filename = read_file_blob('pending_note_path')
            
            if not form and not proposal_data:
                flash("Proposal is required", "error")
                return redirect(url_for('submit_form_b_requirements'))

            if not form:
                form = FormARequirements(user_id=user_id, form_type="FORM B")
                db_session.add(form)
            
            # Update fields
            form.form_type = "FORM B"
            form.needs_permission = needs_permission_bool
            form.has_clearance = has_clearance
            form.has_ethics_evidence = has_ethics_evidence
            form.updated_at = datetime.utcnow()
            
            if permission_letter_data:
                form.permission_letter = permission_letter_data
                form.permission_letter_filename = permission_letter_fname
            
            if prior_clearance_data:
                form.prior_clearance_path = prior_clearance_data
                form.prior_clearance_path_filename = prior_clearance_fname
                
            if ethics_evidence_data:
                form.ethics_evidence_path = ethics_evidence_data
                form.ethics_evidence_path_filename = ethics_evidence_fname
                
            if proposal_data:
                form.proposal_path = proposal_data
                form.proposal_filename = proposal_fname
                
            if pending_note_data:
                form.pending_note = pending_note_data
                form.pending_note_filename = pending_note_filename

            db_session.commit()
            
            if not formB:
                return redirect(url_for('form_b_sec1'))
            return redirect(url_for('student_dashboard'))
            
        except Exception as e:
            traceback.print_exc()
            db_session.rollback()
            flash(f"Error submitting requirements: {str(e)}", "danger")
            return redirect(url_for('submit_form_b_requirements'))
            
    return render_template('form-b-upload.html', from_dashboard=form)

            
@app.route('/edit-form-a/<form_id>', methods=['GET'])
def edit_form_a(form_id):
    data = getFormAData(form_id)
    if data:
        session['active_forma_id'] = data.form_id
    return render_template('form-a-section1.html', form_data=data)



# ---------------- Section 1 ------------------
