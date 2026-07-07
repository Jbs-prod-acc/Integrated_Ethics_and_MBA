from app_support import *

    user_id=session.get('id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    form = db_session.query(FormC).filter_by(user_id=user_id).first()
    return render_template("form_c_answers.html",formc=form)

@app.route('/form_d_answers', methods=['GET','POST'])
def form_d_answers():
    user_id=session.get('id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    form = db_session.query(FormD).filter_by(user_id=user_id).first()
    return render_template("form_d_answers.html",form=form)



@app.route('/api/form-c/<form_id>', methods=['GET'])
@login_required
def get_form_c(form_id):
    form_c = db_session.query(FormC).filter_by(form_id=form_id).first()
    if not form_c:
        return jsonify({"message": "Form not found"}), 404
    if not can_access_form(get_current_user(), form_c):
        return jsonify({"message": "Forbidden"}), 403
    return jsonify(form_c.to_dict()), 200


@app.route('/api/form-c/<form_id>/reassign-reviewers', methods=['POST'])
def api_reassign_form_c_reviewers(form_id):
    user_id = session.get('id')
    user_role = (session.get('role') or '').upper()
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    if user_role not in ['ADMIN', 'SUPER_ADMIN']:
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    form = db_session.query(FormC).filter_by(form_id=form_id).first()
    if not form:
        return jsonify({'success': False, 'error': 'Form C not found'}), 404

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
        page='API Form C Reassignment',
        target_user_id=form.user_id,
        details=f"Reassigned reviewers via API: {form.reviewer_name1}, {form.reviewer_name2} for FORM C {form.form_id}"
    ))
    db_session.commit()

    return jsonify({
        'success': True,
        'message': 'Form C reviewers reassigned successfully',
        'form_id': form.form_id,
        'reviewer_ids': selected_ids
    }), 200



@app.route('/chair_dashboard', methods=['GET','POST'])
def chair_dashboard():
    submitted_form_a = (db_session.query(FormA)
    .filter(FormA.submitted_at != None)
    .all())
    submitted_form_b = (db_session.query(FormB)
    .options(
        defer(FormB.permission_letter),
        defer(FormB.prior_clearance),
        defer(FormB.ethics_evidence),
        defer(FormB.proposal_path),
        defer(FormB.pending_note),
        defer(FormB.private_permission_file)
    )
    .filter(FormB.submitted_at != None)
    .all())
    submitted_form_c = (db_session.query(FormC)
    .filter(FormC.submission_date != None)
    .all())

    today = date.today()
    return render_template('chair-dashboard.html',today=today,submitted_form_a=submitted_form_a,submitted_form_b=submitted_form_b,submitted_form_c=submitted_form_c)


def parse_field(field):
        if field and isinstance(field, str):
            return field.strip("{}").split(",")
        return []


@app.route('/chair_forma_view/<string:id>', methods=['GET'])
def chair_forma_view(id):
    current_form = (
        db_session.query(FormA)
        .filter(
            FormA.user_id == id,
            FormA.submitted_at.isnot(None),
            or_(
                and_(FormA.submitted_to_admin == True, FormA.rejected_or_accepted == True),
                FormA.submitted_to_reviewers == True,
                FormA.form_reviewed_by.isnot(None),
                FormA.form_reviewed_by1.isnot(None),
            )
        )
        .order_by(desc(FormA.submitted_at), desc(FormA.created_at))
        .first()
    )

    form = (
        db_session.query(FormA)
        .filter(
            FormA.user_id == id,
            or_(
                FormA.created_at.isnot(None),
                FormA.submitted_at.isnot(None)
            )
        )
        .order_by(desc(FormA.submitted_at), desc(FormA.created_at))
        .all()
    )

    if not current_form and form:
        current_form = form[0]

    form_name="FORM A"
    data={}
    if current_form:
        data={
        "org_name" : parse_field(current_form.org_name),
        "org_contact" : parse_field(current_form.org_contact),
        "org_role": parse_field(current_form.org_role),
        "org_permission" : parse_field(current_form.org_permission),

        "fund_org" : parse_field(current_form.fund_org),
        "fund_contact" :parse_field(current_form.fund_contact),
        "fund_role": parse_field(current_form.fund_role),
        "fund_amount": parse_field(current_form.fund_amount),

        "population" :parse_field(current_form.population),
        "sampling_method" : parse_field(current_form.sampling_method),
        "sampling_size": parse_field(current_form.sampling_size),
        "inclusion_criteria": parse_field(current_form.inclusion_criteria)
    }
    
    today = date.today()
    user_role = session.get('role', '')
    return render_template(
        "chair-forms-dashboard.html",
        data=data,
        today=today,
        form_name=form_name,
        submitted_form=form,
        current_form_id=current_form.form_id if current_form else None,
        role=user_role
    )


@app.route('/chair_forma_reassign_reviewers/<string:form_id>', methods=['GET', 'POST'])
def chair_forma_reassign_reviewers(form_id):
    form = db_session.query(FormA).filter_by(form_id=form_id).first()
    if not form:
        flash("Form A record not found.", "danger")
        return redirect(url_for('chair_dashboard'))

    reviewers = (
        db_session.query(User)
        .filter(User.role == UserRole.REVIEWER)
        .order_by(User.full_name.asc())
        .all()
    )

    current_reviewer_ids = [rid for rid in [form.reviewer_name1, form.reviewer_name2] if rid]
    current_reviewers = []
    if current_reviewer_ids:
        current_reviewers = (
            db_session.query(User)
            .filter(User.user_id.in_(current_reviewer_ids))
            .all()
        )

    if request.method == 'POST':
        selected_ids = []
        for reviewer_id in request.form.getlist('reviewer_names[]'):
            reviewer_id = (reviewer_id or '').strip()
            if reviewer_id and reviewer_id not in selected_ids:
                selected_ids.append(reviewer_id)

        if len(selected_ids) < 1 or len(selected_ids) > 2:
            flash("Please select one or two reviewers.", "danger")
            return render_template(
                'chair-forma-reassign-reviewers.html',
                form=form,
                reviewers=reviewers,
                current_reviewers=current_reviewers,
                selected_reviewer_ids=selected_ids
            )

        selected_reviewers = (
            db_session.query(User)
            .filter(
                User.user_id.in_(selected_ids),
                User.role == UserRole.REVIEWER
            )
            .all()
        )

        if len(selected_reviewers) != len(selected_ids):
            flash("One or more selected reviewers are invalid.", "danger")
            return render_template(
                'chair-forma-reassign-reviewers.html',
                form=form,
                reviewers=reviewers,
                current_reviewers=current_reviewers,
                selected_reviewer_ids=selected_ids
            )

        form.reviewer_name1 = selected_ids[0]
        form.reviewer_name2 = selected_ids[1] if len(selected_ids) > 1 else None
        form.submitted_to_reviewers = True

        db_session.add(UserActivityLog(
            user_id=session.get('id'),
            action='reassign_reviewers',
            page='Chair Form A View',
            target_user_id=form.user_id,
            details=f"Reassigned reviewers: {form.reviewer_name1}, {form.reviewer_name2} for FORM A {form.form_id}"
        ))
        db_session.commit()

        flash("Reviewers reassigned successfully.", "success")
        return redirect(url_for('chair_forma_view', id=form.user_id))

    return render_template(
        'chair-forma-reassign-reviewers.html',
        form=form,
        form_name='FORM A',
        reviewers=reviewers,
        current_reviewers=current_reviewers,
        selected_reviewer_ids=current_reviewer_ids
    )


@app.route('/chair_formb_reassign_reviewers/<string:form_id>', methods=['GET', 'POST'])
def chair_formb_reassign_reviewers(form_id):
    form = db_session.query(FormB).filter_by(form_id=form_id).first()
    if not form:
        flash("Form B record not found.", "danger")
        return redirect(url_for('chair_dashboard'))

    reviewers = (
        db_session.query(User)
        .filter(User.role == UserRole.REVIEWER)
        .order_by(User.full_name.asc())
        .all()
    )

    current_reviewer_ids = [rid for rid in [form.reviewer_name1, form.reviewer_name2] if rid]
    current_reviewers = []
    if current_reviewer_ids:
        current_reviewers = (
            db_session.query(User)
            .filter(User.user_id.in_(current_reviewer_ids))
            .all()
        )

    if request.method == 'POST':
        selected_ids = []
        for reviewer_id in request.form.getlist('reviewer_names[]'):
            reviewer_id = (reviewer_id or '').strip()
            if reviewer_id and reviewer_id not in selected_ids:
                selected_ids.append(reviewer_id)

        if len(selected_ids) < 1 or len(selected_ids) > 2:
            flash("Please select one or two reviewers.", "danger")
            return render_template(
                'chair-forma-reassign-reviewers.html',
                form=form,
                form_name='FORM B',
                reviewers=reviewers,
                current_reviewers=current_reviewers,
                selected_reviewer_ids=selected_ids
            )

        selected_reviewers = (
            db_session.query(User)
            .filter(
                User.user_id.in_(selected_ids),
                User.role == UserRole.REVIEWER
            )
            .all()
        )

        if len(selected_reviewers) != len(selected_ids):
            flash("One or more selected reviewers are invalid.", "danger")
            return render_template(
                'chair-forma-reassign-reviewers.html',
                form=form,
                form_name='FORM B',
                reviewers=reviewers,
                current_reviewers=current_reviewers,
                selected_reviewer_ids=selected_ids
            )

        form.reviewer_name1 = selected_ids[0]
        form.reviewer_name2 = selected_ids[1] if len(selected_ids) > 1 else None
        form.submitted_to_reviewers = True

        db_session.add(UserActivityLog(
            user_id=session.get('id'),
            action='reassign_reviewers',
            page='Chair Form B View',
            target_user_id=form.user_id,
            details=f"Reassigned reviewers: {form.reviewer_name1}, {form.reviewer_name2} for FORM B {form.form_id}"
        ))
        db_session.commit()

        flash("Reviewers reassigned successfully.", "success")
        return redirect(url_for('chair_formb_view', id=form.user_id))

    return render_template(
        'chair-forma-reassign-reviewers.html',
        form=form,
        form_name='FORM B',
        reviewers=reviewers,
        current_reviewers=current_reviewers,
        selected_reviewer_ids=current_reviewer_ids
    )


@app.route('/chair_formc_reassign_reviewers/<string:form_id>', methods=['GET', 'POST'])
def chair_formc_reassign_reviewers(form_id):
    form = db_session.query(FormC).filter_by(form_id=form_id).first()
    if not form:
        flash("Form C record not found.", "danger")
        return redirect(url_for('chair_dashboard'))

    reviewers = (
        db_session.query(User)
        .filter(User.role == UserRole.REVIEWER)
        .order_by(User.full_name.asc())
        .all()
    )

    current_reviewer_ids = [rid for rid in [form.reviewer_name1, form.reviewer_name2] if rid]
    current_reviewers = []
    if current_reviewer_ids:
        current_reviewers = (
            db_session.query(User)
            .filter(User.user_id.in_(current_reviewer_ids))
            .all()
        )

    if request.method == 'POST':
        selected_ids = []
        for reviewer_id in request.form.getlist('reviewer_names[]'):
            reviewer_id = (reviewer_id or '').strip()
            if reviewer_id and reviewer_id not in selected_ids:
                selected_ids.append(reviewer_id)

        if len(selected_ids) < 1 or len(selected_ids) > 2:
            flash("Please select one or two reviewers.", "danger")
            return render_template(
                'chair-forma-reassign-reviewers.html',
                form=form,
                form_name='FORM C',
                reviewers=reviewers,
                current_reviewers=current_reviewers,
                selected_reviewer_ids=selected_ids
            )

        selected_reviewers = (
            db_session.query(User)
            .filter(
                User.user_id.in_(selected_ids),
                User.role == UserRole.REVIEWER
            )
            .all()
        )

        if len(selected_reviewers) != len(selected_ids):
            flash("One or more selected reviewers are invalid.", "danger")
            return render_template(
                'chair-forma-reassign-reviewers.html',
                form=form,
                form_name='FORM C',
                reviewers=reviewers,
                current_reviewers=current_reviewers,
                selected_reviewer_ids=selected_ids
            )

        form.reviewer_name1 = selected_ids[0]
        form.reviewer_name2 = selected_ids[1] if len(selected_ids) > 1 else None
        form.submitted_to_reviewers = True

        db_session.add(UserActivityLog(
            user_id=session.get('id'),
            action='reassign_reviewers',
            page='Chair Form C View',
            target_user_id=form.user_id,
            details=f"Reassigned reviewers: {form.reviewer_name1}, {form.reviewer_name2} for FORM C {form.form_id}"
        ))
        db_session.commit()

        flash("Reviewers reassigned successfully.", "success")
        return redirect(url_for('chair_formc_view', id=form.user_id))

    return render_template(
        'chair-forma-reassign-reviewers.html',
        form=form,
        form_name='FORM C',
        reviewers=reviewers,
        current_reviewers=current_reviewers,
        selected_reviewer_ids=current_reviewer_ids
    )


@app.route('/chair_formb_view/<string:id>', methods=['GET'])
def chair_formb_view(id):
    form = (
        db_session.query(FormB)
        .options(
            defer(FormB.permission_letter),
            defer(FormB.prior_clearance),
            defer(FormB.ethics_evidence),
            defer(FormB.proposal_path),
            defer(FormB.pending_note),
            defer(FormB.private_permission_file)
        )
        .filter(FormB.user_id==id and FormB.submitted_at != None,FormB.submitted_to_admin==True)
        .order_by(desc(FormB.submitted_at))
        .all())
    form_name="FORM B"
    today = date.today()
    user_role = session.get('role', '')
    return render_template("chair-forms-dashboard.html",today=today,form_name=form_name,submitted_form=form,role=user_role)

@app.route('/chair_formc_view/<string:id>', methods=['GET'])
def chair_formc_view(id):
    form = (
        db_session.query(FormC)
        .filter(FormC.user_id==id and FormC.submission_date != None,FormC.submitted_to_admin==True)
        .order_by(desc(FormC.submission_date))
        .all())
    form_name="FORM C"
    
    today = date.today()
    user_role = session.get('role', '')
    return render_template("chair-forms-dashboard.html",today=today,form_name=form_name,submitted_form=form,role=user_role)

# Unified endpoint to view all forms for a user
@app.route('/chair_form_view_fixed/<string:user_id>', methods=['GET'])
def chair_form_view_fixed(user_id):
    # Query all forms for the user
    form_a_list = db_session.query(FormA).filter_by(user_id=user_id).order_by(FormA.submitted_at.desc()).all()
    form_b_list = db_session.query(FormB).filter_by(user_id=user_id).order_by(FormB.submitted_at.desc()).all()
    form_c_list = db_session.query(FormC).filter_by(user_id=user_id).order_by(FormC.submission_date.desc()).all()

    user = db_session.query(User).filter_by(user_id=user_id).first()
    user_name = user.full_name if user else "Unknown"

    return render_template(
        "chair-forms-view-fixed.html",
        user_id=user_id,
        user_name=user_name,
        form_a_list=form_a_list,
        form_b_list=form_b_list,
        form_c_list=form_c_list
    )


@app.route("/send_certificate/<string:id>",methods=['POST'])
def send_certificate(id):
    if request.method=='POST':
        certificate_details = None
        for model in [FormA, FormB, FormC]:
            
            certificate_details = db_session.query(model).filter_by(form_id=id).first()
            #user=db_session.query(User).filter(certificate_details.user_id==id).first()

            if certificate_details:    
                certificate_details.certificate_received=True
                certificate_details.certificate_modified=False
                db_session.commit()
                
                #Uncomment the code bellow for testing
                ##
                try:
                    message=(f'You have been issued with the Ethical Clearance Certificate. '
                    f'Please follow the link {web_url} to view your certificate.')
                    if certificate_details.email:
                        send_email(app,mail, message,[certificate_details.email])
                    elif certificate_details.email_address:
                        send_email(app,mail, message,[certificate_details.email_address])
                except Exception as e:
                    app.logger.error(f"Failed to send email : {e}")
        return redirect(url_for('chair_landing'))



@app.route("/faq",methods=['GET','POST'])
def faq():
    return render_template("faq.html")



@app.route('/student_view_feedback/<string:id>', methods=['GET'])
def student_view_feedback(id):
    form = None
    for model in [FormA, FormB, FormC]:
        form = db_session.query(model).filter_by(form_id=id).first()
        if form:
            break  # Stop once the form is found

    if form:
        form = merge_reviewer_feedback_from_related_draft(form)
        return render_template("student-view-feedback.html", view_form=form)
    else:
        # You can pass an error message or just load the dashboard
        return redirect(url_for('dashboard'))


@app.route('/supervisor_view_feedback/<string:id>', methods=['GET'])
def supervisor_view_feedback(id):
    form = None
    for model in [FormA, FormB, FormC]:
        order_field = getattr(model, "submitted_at", getattr(model, "submission_date", None))
        if not order_field:
            continue
        form = (
            db_session.query(model)
            .filter_by(form_id=id)
            .order_by(order_field.desc())
            .first()
        )
        if form:
            break


    if form:
        form = merge_reviewer_feedback_from_related_draft(form)
        return render_template("supervisor-view-feedback.html", view_form=form)
    else:
        # You can pass an error message or just load the dashboard
        return redirect(url_for('supervisor_dashboard'))


@app.route('/ethics_view_feedback/<string:id>', methods=['GET'])
def ethics_view_feedback(id):
    form = None
    for model in [FormA, FormB, FormC]:
        # pick whichever timestamp column the model has
        order_field = getattr(model, "submitted_at", getattr(model, "submission_date", None))
        if not order_field:
            continue  # skip if model doesn't have a timestamp field

        form = (
            db_session.query(model)
            .filter_by(form_id=id)
            .order_by(order_field.desc())
            .first()
        )
        if form:
            break
  

    if form:
        form = merge_reviewer_feedback_from_related_draft(form)
        return render_template("ethics-view-feedback.html", view_form=form)
    else:
        # You can pass an error message or just load the dashboard
        return redirect(url_for('chair_landing'))


###
###
### this is the function to focus on when intergrating MBA and Ethics
###
@app.route('/reviewer_list/', methods=['GET'])
def reviewer_list():
    user_id=session.get('id')
    user_profile=db_session.query(User).filter_by(user_id=user_id).first()
    form = db_session.query(User).filter(User.role=="REVIEWER").all()
       
    role=user_profile.role.value
    return render_template("reviewer-list.html",role=role,user_profile=user_profile, view_form=form)
   


@app.route('/review_feedback/<string:form_id>', methods=['GET','POST'])
def review_feedback(form_id):
    user_id=session.get('id')
    
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    form = None
    for model in [FormA, FormB, FormC]:
        form = db_session.query(model).filter_by(form_id=form_id).first()
        if form:
            break  # Stop once the form is found
    
    if form:
        form = merge_reviewer_feedback_from_related_draft(form)
        first_reviewer=''
        second_reveiwer=''
        if user_id == form.reviewer_name1 and user_id != form.reviewer_name2:
            first_reviewer=user_id
        elif user_id == form.reviewer_name2 and user_id != form.reviewer_name1:
            second_reveiwer=user_id
        return render_template("reviewer_feedback.html",view_form=form,first=first_reviewer,second=second_reveiwer)
    else:
        # You can pass an error message or just load the dashboard
        return redirect(url_for('review_version'))
    


@app.route('/chair_form_view/<string:id>/<string:form_name>', methods=['GET','POST'])
def chair_form_view(id,form_name):
    user_id=session.get('id')
    if not user_id:
        return redirect('/login?system=ethics')

    user_name=db_session.query(User).filter_by(user_id=user_id).first()
    if not user_name:
        session.clear()
        return redirect('/login?system=ethics')

    user_role = getattr(getattr(user_name, 'role', None), 'value', '')
    forma = db_session.query(FormA).filter_by(form_id=id).first()
    formb = db_session.query(FormB).options(
        defer(FormB.permission_letter),
        defer(FormB.prior_clearance),
        defer(FormB.ethics_evidence),
        defer(FormB.proposal_path),
        defer(FormB.pending_note),
        defer(FormB.private_permission_file)
    ).filter_by(form_id=id).first()
    formc = db_session.query(FormC).filter_by(form_id=id).first()

    if forma:
        formReviewers = db_session.query(User).filter(
        and_(
            User.role == "REVIEWER",
            User.email != forma.supervisor_email,
            User.authenticate_student.in_(['true', '1'])
        )
        ).all()
    elif formb:
        formReviewers = db_session.query(User).filter(
        and_(
            User.role == "REVIEWER",
            User.email != formb.supervisor_email,
            User.authenticate_student.in_(['true', '1'])
        )
            ).all()
    elif formc:
        formReviewers = db_session.query(User).filter(
        and_(
            User.role == "REVIEWER",
            User.email != formc.supervisor_email,
            User.authenticate_student.in_(['true', '1'])
        )
        ).all()
    
    list_of_revewers=[]
    id_of_reviewers=[]
    data={}
    if forma:
        data={
        "org_name" : parse_field(forma.org_name),
        "org_contact" : parse_field(forma.org_contact),
        "org_role": parse_field(forma.org_role),
        "org_permission" : parse_field(forma.org_permission),

        "fund_org" : parse_field(forma.fund_org),
        "fund_contact" :parse_field(forma.fund_contact),
        "fund_role": parse_field(forma.fund_role),
        "fund_amount": parse_field(forma.fund_amount),

        "population" :parse_field(forma.population),
        "sampling_method" : parse_field(forma.sampling_method),
        "sampling_size": parse_field(forma.sampling_size),
        "inclusion_criteria": parse_field(forma.inclusion_criteria)
    }

        
       
        latest_forma = db_session.query(FormA) \
        .filter(FormA.user_id == forma.user_id) \
        .order_by(FormA.submitted_at.asc()) \
        .first()
        Assigned_reviewer=db_session.query(User).filter(User.user_id.in_([latest_forma.reviewer_name1, latest_forma.reviewer_name2])).all()
        if Assigned_reviewer:
            for item in Assigned_reviewer:
                list_of_revewers.append(item.email)
                id_of_reviewers.append(item.user_id)
   
    #admin=db_session.query(User).filter_by(role="Admin").all()
    if form_name=="FORM A":
        
   
        if request.method=="POST":
           
            review_date=datetime.now()
            status=request.form.get('status')
            review_org_permission_status=request.form.get('org_permission_status')
            review_org_permission_comments=request.form.get('org_permission_comments')
            review_waiver_status=request.form.get('waiver_status')
            form_status=request.form.get('form_status')
            review_waiver_comments=request.form.get('waiver_comments')
            review_form_status=request.form.get('reject')
            review_form_comments=request.form.get('form_comments')
            review_questions_status=request.form.get('questions_status')
            review_questions_comments=request.form.get('questions_comments')
            review_consent_status=request.form.get('consent_status')
            review_consent_comments=request.form.get('consent_comments')
            review_proposal_status=request.form.get('proposal_status')
            review_proposal_comments=request.form.get('proposal_comments')
            review_additional_comments=request.form.get('additional_comments')
            review_recommendation=request.form.get('status')
            review_supervisor_signature=request.form.get('supervisor_signature')
            review_signature_date=datetime.now()
            form_review_comment=request.form.get('status')
            form_reviewed_by=user_id
 
            if request.form.get('status') in ['Approved','Approved with Minor Changes']:
                if str(user_id) == str(forma.reviewer_name1):
                    forma.review_date=review_date
                    forma.status=status
                    forma.review_org_permission_status=review_org_permission_status
                    forma.review_org_permission_comments=review_org_permission_comments
                    forma.review_waiver_status=review_waiver_status
                    forma.form_status=form_status
                    forma.review_waiver_comments=review_waiver_comments
                    forma.review_form_status=review_form_status
                    forma.review_form_comments=review_form_comments
                    forma.review_questions_status=review_questions_status
                    forma.review_questions_comments=review_questions_comments
                    forma.review_consent_status=review_consent_status
                    forma.review_consent_comments=review_consent_comments
                    forma.review_proposal_status=review_proposal_status
                    forma.review_proposal_comments=review_proposal_comments
                    forma.review_additional_comments=review_additional_comments
                    forma.review_recommendation=review_recommendation
                    forma.review_supervisor_signature=review_supervisor_signature
                    forma.review_signature_date=review_signature_date
                    forma.form_review_comment=form_review_comment
                    forma.form_reviewed_by=form_reviewed_by
                    forma.review_status=True
                    forma.rejected_or_accepted=True

                    #Uncomment the code bellow for testing
                    ##
                  
                    #add coments to Rec table
                    if user_role=='REVIEWER':
                       
                        form=Rec(
                        rec_id=user_id,
                        form_id=id,
                        full_name=user_name.full_name,
                        rec_comments = review_additional_comments,
                        rec_status = status,
                        rec_date=datetime.now()
                        )
                        db_session.add(form)
                   
                else:
                    forma.review_date1=review_date
                    forma.status=status
                    forma.review_org_permission_status1=review_org_permission_status
                    forma.review_org_permission_comments1=review_org_permission_comments
                    forma.review_waiver_status1=review_waiver_status
                    forma.form_status1=form_status
                    forma.review_waiver_comments1=review_waiver_comments
                    forma.review_form_status1=review_form_status
                    forma.review_form_comments1=review_form_comments
                    forma.review_questions_status1=review_questions_status
                    forma.review_questions_comments1=review_questions_comments
                    forma.review_consent_status1=review_consent_status
                    forma.review_consent_comments1=review_consent_comments
                    forma.review_proposal_status1=review_proposal_status
                    forma.review_proposal_comments1=review_proposal_comments
                    forma.review_additional_comments1=review_additional_comments
                    forma.review_recommendation1=review_recommendation
                    forma.review_supervisor_signature1=review_supervisor_signature
                    forma.review_signature_date1=review_signature_date
                    forma.form_review_comment1=form_review_comment
                    forma.form_reviewed_by1=form_reviewed_by
                    forma.review_status1=True
                    forma.rejected_or_accepted=True
                  

                    #Uncomment the code bellow for testing
                    ##
                    
                    #add coments to Rec table
                    if user_role=='REVIEWER':
                     
                        form=Rec(
                        rec_id=user_id,
                        form_id=id,
                        full_name=user_name.full_name,
                        rec_comments = review_additional_comments,
                        rec_status = status,
                        rec_date=datetime.now()
                        )
                        db_session.add(form)
                   
            else:
                if str(user_id) == str(forma.reviewer_name1):
                    forma.review_date=review_date
                    forma.status=status
                    forma.review_org_permission_status=review_org_permission_status
                    forma.review_org_permission_comments=review_org_permission_comments
                    forma.review_waiver_status=review_waiver_status
                    forma.form_status=form_status
                    forma.review_waiver_comments=review_waiver_comments
                    forma.review_form_status=review_form_status
                    forma.review_form_comments=review_form_comments
                    forma.review_questions_status=review_questions_status
                    forma.review_questions_comments=review_questions_comments
                    forma.review_consent_status=review_consent_status
                    forma.review_consent_comments=review_consent_comments
                    forma.review_proposal_status=review_proposal_status
                    forma.review_proposal_comments=review_proposal_comments
                    forma.review_additional_comments=review_additional_comments
                    forma.review_recommendation=review_recommendation
                    forma.form_review_comment=form_review_comment
                    forma.form_reviewed_by=form_reviewed_by
                    forma.review_status=False
                    forma.rejected_or_accepted=False

                    #Uncomment the code bellow for testing
                    ##
                    
                    try:
                        emails_of_student_and_supervisor=[]
                        emails_of_student_and_supervisor.append(forma.email)
                        emails_of_student_and_supervisor.append(forma.supervisor_email)
                        message=f' Form belonging to {forma.applicant_name} was sent back. Please view feedback.'
            
                        send_email(app,mail, message,emails_of_student_and_supervisor)
                    except Exception as e:
                        app.logger.error(f"Failed to send email")
                        
                else:
                    forma.review_date1=review_date
                    forma.status=status
                    forma.review_org_permission_status1=review_org_permission_status
                    forma.review_org_permission_comments1=review_org_permission_comments
                    forma.review_waiver_status1=review_waiver_status
                    forma.form_status1=form_status
                    forma.review_waiver_comments1=review_waiver_comments
                    forma.review_form_status1=review_form_status
                    forma.review_form_comments1=review_form_comments
                    forma.review_questions_status1=review_questions_status
                    forma.review_questions_comments1=review_questions_comments
                    forma.review_consent_status1=review_consent_status
                    forma.review_consent_comments1=review_consent_comments
                    forma.review_proposal_status1=review_proposal_status
                    forma.review_proposal_comments1=review_proposal_comments
                    forma.review_additional_comments1=review_additional_comments
                    forma.review_recommendation1=review_recommendation
                    forma.review_supervisor_signature1=review_supervisor_signature
                    forma.review_signature_date1=review_signature_date
                    forma.form_review_comment1=form_review_comment
                    forma.form_reviewed_by1=form_reviewed_by
                    forma.review_status=False
                    forma.rejected_or_accepted=False

                    #Uncomment the code bellow for testing
                    ##
                    
                   
                    try:
                        emails_of_student_and_supervisor=[]
                        emails_of_student_and_supervisor.append(forma.email)
                        emails_of_student_and_supervisor.append(forma.supervisor_email)
                        message=f' Form belonging to {forma.applicant_name} was sent back. Please view feedback.'
            
                        send_email(app,mail, message,emails_of_student_and_supervisor)
                    except Exception as e:
                        app.logger.error(f"Failed to send email")   
                

                #add coments to Rec table
                if user_role=='REVIEWER':
                       
                        form=Rec(
                        rec_id=user_id,
                        form_id=id,
                        full_name=user_name.full_name,
                        rec_comments = review_additional_comments,
                        rec_status = status,
                        rec_date=datetime.now()
                        )
                        db_session.add(form)
            db_session.add(forma)
            db_session.commit()

            
            
            return redirect(url_for('review_dashboard'))
        return render_template("form_a_ethics.html",user_id=user_id,formA=forma,data=data,formReviewers=formReviewers,latest_forma=latest_forma)
    elif form_name=="FORM B":
        
        if formb:
            latest_formb = db_session.query(FormB) \
            .filter(FormB.user_id == formb.user_id) \
            .order_by(FormB.submitted_at.asc()) \
            .first()
            Assigned_reviewer=db_session.query(User).filter(User.user_id.in_([latest_formb.reviewer_name1, latest_formb.reviewer_name2])).all()
            if Assigned_reviewer:
                for item in Assigned_reviewer:
                    list_of_revewers.append(item.email)
                    id_of_reviewers.append(item.user_id)
        if request.method=="POST":
            review_date=datetime.now()
            status=request.form.get('status')
            review_org_permission_status=request.form.get('org_permission_status')
            review_org_permission_comments=request.form.get('org_permission_comments')
            review_waiver_status=request.form.get('waiver_status')
            form_status=request.form.get('form_status')
            review_waiver_comments=request.form.get('waiver_comments')
            review_form_status=request.form.get('reject')
            review_form_comments=request.form.get('form_comments')
            review_questions_status=request.form.get('questions_status')
            review_questions_comments=request.form.get('questions_comments')
            review_consent_status=request.form.get('consent_status')
            review_consent_comments=request.form.get('consent_comments')
            review_proposal_status=request.form.get('proposal_status')
            review_proposal_comments=request.form.get('proposal_comments')
            review_additional_comments=request.form.get('additional_comments')
            review_recommendation=request.form.get('status')
            review_supervisor_signature=request.form.get('supervisor_signature')
            review_signature_date=datetime.now()
            form_review_comment=request.form.get('status')
            form_reviewed_by=user_id
            if request.form.get('status') in ['Approved','Approved with Minor Changes']:
                if str(user_id) == str(formb.reviewer_name1):
                    formb.review_date=review_date
                    formb.status=status
                    formb.review_org_permission_status=review_org_permission_status
                    formb.review_org_permission_comments=review_org_permission_comments
                    formb.review_waiver_status=review_waiver_status
                    formb.form_status=form_status
                    formb.review_waiver_comments=review_waiver_comments
                    formb.review_form_status=review_form_status
                    formb.review_form_comments=review_form_comments
                    formb.review_questions_status=review_questions_status
                    formb.review_questions_comments=review_questions_comments
                    formb.review_consent_status=review_consent_status
                    formb.review_consent_comments=review_consent_comments
                    formb.review_proposal_status=review_proposal_status
                    formb.review_proposal_comments=review_proposal_comments
                    formb.review_additional_comments=review_additional_comments
                    formb.review_recommendation=review_recommendation
                    formb.review_supervisor_signature=review_supervisor_signature
                    formb.review_signature_date=review_signature_date
                    formb.form_review_comment=form_review_comment
                    formb.form_reviewed_by=form_reviewed_by
                    formb.review_status=True
                    formb.rejected_or_accepted=True
                    #Uncomment the code bellow for testing
                    ##
                        
                    #add coments to Rec table
                    if user_role=='REVIEWER':
                       
                        form=Rec(
                        rec_id=user_id,
                        form_id=id,
                        full_name=user_name.full_name,
                        rec_comments = review_additional_comments,
                        rec_status = status,
                        rec_date=datetime.now()
                        )
                        db_session.add(form)
                else:
                    formb.review_date1=review_date
                    formb.status=status
                    formb.review_org_permission_status1=review_org_permission_status
                    formb.review_org_permission_comments1=review_org_permission_comments
                    formb.review_waiver_status1=review_waiver_status
                    formb.form_status1=form_status
                    formb.review_waiver_comments1=review_waiver_comments
                    formb.review_form_status1=review_form_status
                    formb.review_form_comments1=review_form_comments
                    formb.review_questions_status1=review_questions_status
                    formb.review_questions_comments1=review_questions_comments
                    formb.review_consent_status1=review_consent_status
                    formb.review_consent_comments1=review_consent_comments
                    formb.review_proposal_status1=review_proposal_status
                    formb.review_proposal_comments1=review_proposal_comments
                    formb.review_additional_comments1=review_additional_comments
                    formb.review_recommendation1=review_recommendation
                    formb.review_supervisor_signature1=review_supervisor_signature
                    formb.review_signature_date1=review_signature_date
                    formb.form_review_comment1=form_review_comment
                    formb.form_reviewed_by1=form_reviewed_by
                    formb.review_status1=True
                    formb.rejected_or_accepted=True

                    #Uncomment the code bellow for testing
                    ##
                    
                    #add coments to Rec table
                    if user_role=='REVIEWER':
                        form=Rec(
                        rec_id=user_id,
                        form_id=id,
                        full_name=user_name.full_name,
                        rec_comments = review_additional_comments,
                        rec_status = status,
                        rec_date=datetime.now()
                        )
                        db_session.add(form)
                   
            else:
                if str(user_id) == str(formb.reviewer_name1):
                    formb.review_date=review_date
                    formb.status=status
                    formb.review_org_permission_status=review_org_permission_status
                    formb.review_org_permission_comments=review_org_permission_comments
                    formb.review_waiver_status=review_waiver_status
                    formb.form_status=form_status
                    formb.review_waiver_comments=review_waiver_comments
                    formb.review_form_status=review_form_status
                    formb.review_form_comments=review_form_comments
                    formb.review_questions_status=review_questions_status
                    formb.review_questions_comments=review_questions_comments
                    formb.review_consent_status=review_consent_status
                    formb.review_consent_comments=review_consent_comments
                    formb.review_proposal_status=review_proposal_status
                    formb.review_proposal_comments=review_proposal_comments
                    formb.review_additional_comments=review_additional_comments
                    formb.review_recommendation=review_recommendation
                    formb.form_review_comment=form_review_comment
                    formb.form_reviewed_by=form_reviewed_by
                    formb.review_status=False
                    formb.rejected_or_accepted=False

                    #Uncomment the code bellow for testing
                    ##
                    
                    try:
                        emails_of_student_and_supervisor=[]
                        emails_of_student_and_supervisor.append(formb.email)
                        emails_of_student_and_supervisor.append(formb.supervisor_email)
                        message=f' Form belonging to {formb.applicant_name} was sent back. Please view feedback.'
            
                        send_email(app,mail, message,emails_of_student_and_supervisor)
                    except Exception as e:
                        app.logger.error(f"Failed to send email")
                else:
                    formb.review_date1=review_date
                    formb.status=status
                    formb.review_org_permission_status1=review_org_permission_status
                    formb.review_org_permission_comments1=review_org_permission_comments
                    formb.review_waiver_status1=review_waiver_status
                    formb.form_status1=form_status
                    formb.review_waiver_comments1=review_waiver_comments
                    formb.review_form_status1=review_form_status
                    formb.review_form_comments1=review_form_comments
                    formb.review_questions_status1=review_questions_status
                    formb.review_questions_comments1=review_questions_comments
                    formb.review_consent_status1=review_consent_status
                    formb.review_consent_comments1=review_consent_comments
                    formb.review_proposal_status1=review_proposal_status
                    formb.review_proposal_comments1=review_proposal_comments
                    formb.review_additional_comments1=review_additional_comments
                    formb.review_recommendation1=review_recommendation
                    formb.review_supervisor_signature1=review_supervisor_signature
                    formb.review_signature_date1=review_signature_date
                    formb.form_review_comment1=form_review_comment
                    formb.form_reviewed_by1=form_reviewed_by
                    formb.review_status=False
                    formb.rejected_or_accepted=False

                    #Uncomment the code bellow for testing
                    ##
                    
                    try:
                        emails_of_student_and_supervisor=[]
                        emails_of_student_and_supervisor.append(formb.email)
                        emails_of_student_and_supervisor.append(formb.supervisor_email)
                        message=f' Form belonging to {formb.applicant_name} was sent back. Please view feedback.'
            
                        send_email(app,mail, message,emails_of_student_and_supervisor)
                    except Exception as e:
                        app.logger.error(f"Failed to send email")
                #add coments to Rec table
                if user_role=='REVIEWER':
                        form=Rec(
                        rec_id=user_id,
                        form_id=id,
                        full_name=user_name.full_name,
                        rec_comments = review_additional_comments,
                        rec_status = status,
                        rec_date=datetime.now()
                        )
                        db_session.add(form)
            db_session.add(formb)
            db_session.commit()
            return redirect(url_for('review_dashboard'))
        return render_template("form_b_ethics.html",user_id=user_id,formB=formb,formReviewers=formReviewers,latest_formb=latest_formb)
    elif form_name=="FORM C":
        
        list_of_revewers=[]
        id_of_reviewers=[]
        if formc:
            latest_formc = db_session.query(FormC) \
            .filter(FormC.user_id == formc.user_id) \
            .order_by(FormC.submission_date.asc()) \
            .first()
            Assigned_reviewer=db_session.query(User).filter(User.user_id.in_([latest_formc.reviewer_name1, latest_formc.reviewer_name2])).all()
            
            if Assigned_reviewer:
                for item in Assigned_reviewer:
                    list_of_revewers.append(item.email)
                    id_of_reviewers.append(item.user_id)
        
        if request.method=="POST":
            
            review_date=datetime.now()
            status=request.form.get('status')
            review_org_permission_status=request.form.get('org_permission_status')
            review_org_permission_comments=request.form.get('org_permission_comments')
            review_waiver_status=request.form.get('waiver_status')
            form_status=request.form.get('form_status')
            review_waiver_comments=request.form.get('waiver_comments')
            review_form_status=request.form.get('reject')
            review_form_comments=request.form.get('form_comments')
            review_questions_status=request.form.get('questions_status')
            review_questions_comments=request.form.get('questions_comments')
            review_consent_status=request.form.get('consent_status')
            review_consent_comments=request.form.get('consent_comments')
            review_proposal_status=request.form.get('proposal_status')
            review_proposal_comments=request.form.get('proposal_comments')
            review_additional_comments=request.form.get('additional_comments')
            review_recommendation=request.form.get('status')
            review_supervisor_signature=request.form.get('supervisor_signature')
           
            review_signature_date=datetime.now()
            form_review_comment=request.form.get('status')
            form_reviewed_by=user_id
            if request.form.get('status') in ['Approved', 'Approved with Minor Changes']:
                
                if str(user_id) == str(formc.reviewer_name1):
                    formc.review_date=review_date
                    formc.status=status
                    formc.review_org_permission_status=review_org_permission_status
                    formc.review_org_permission_comments=review_org_permission_comments
                    formc.review_waiver_status=review_waiver_status
                    formc.form_status=form_status
                    formc.review_waiver_comments=review_waiver_comments
                    formc.review_form_status=review_form_status
                    formc.review_form_comments=review_form_comments
                    formc.review_questions_status=review_questions_status
                    formc.review_questions_comments=review_questions_comments
                    formc.review_consent_status=review_consent_status
                    formc.review_consent_comments=review_consent_comments
                    formc.review_proposal_status=review_proposal_status
                    formc.review_proposal_comments=review_proposal_comments
                    formc.review_additional_comments=review_additional_comments
                    formc.review_recommendation=review_recommendation
                    formc.review_supervisor_signature=review_supervisor_signature
                    formc.review_signature_date=review_signature_date
                    formc.form_review_comment=form_review_comment
                    formc.form_reviewed_by=form_reviewed_by
                    formc.review_status=True
                    formc.rejected_or_accepted=True

                    #Uncomment the code bellow for testing
                    
 
                    #add coments to Rec table
                    if user_role=='REVIEWER':
                        form=Rec(
                        rec_id=user_id,
                        form_id=id,
                        full_name=user_name.full_name,
                        rec_comments = review_additional_comments,
                        rec_status = status,
                        rec_date=datetime.now()
                        )
                        db_session.add(form)
                else:
                    formc.review_date1=review_date
                    formc.status=status
                    formc.review_org_permission_status1=review_org_permission_status
                    formc.review_org_permission_comments1=review_org_permission_comments
                    formc.review_waiver_status1=review_waiver_status
                    formc.form_status1=form_status
                    formc.review_waiver_comments1=review_waiver_comments
                    formc.review_form_status1=review_form_status
                    formc.review_form_comments1=review_form_comments
                    formc.review_questions_status1=review_questions_status
                    formc.review_questions_comments1=review_questions_comments
                    formc.review_consent_status1=review_consent_status
                    formc.review_consent_comments1=review_consent_comments
                    formc.review_proposal_status1=review_proposal_status
                    formc.review_proposal_comments1=review_proposal_comments
                    formc.review_additional_comments1=review_additional_comments
                    formc.review_recommendation1=review_recommendation
                    formc.review_supervisor_signature1=review_supervisor_signature
                    formc.review_signature_date1=review_signature_date
                    formc.form_review_comment1=form_review_comment
                    formc.form_reviewed_by1=form_reviewed_by
                    formc.review_status1=True
                    formc.rejected_or_accepted=True

                    #Uncomment the code bellow for testing
                    ##
                    
                    #add coments to Rec table
                    if user_role=='REVIEWER':
                        form=Rec(
                        rec_id=user_id,
                        form_id=id,
                        full_name=user_name.full_name,
                        rec_comments = review_additional_comments,
                        rec_status = status,
                        rec_date=datetime.now()
                        )
                        db_session.add(form)
                   
            else:
                if str(user_id) == str(formc.reviewer_name1):
                    formc.review_date=review_date
                    formc.status=status
                    formc.review_org_permission_status=review_org_permission_status
                    formc.review_org_permission_comments=review_org_permission_comments
                    formc.review_waiver_status=review_waiver_status
                    formc.form_status=form_status
                    formc.review_waiver_comments=review_waiver_comments
                    formc.review_form_status=review_form_status
                    formc.review_form_comments=review_form_comments
                    formc.review_questions_status=review_questions_status
                    formc.review_questions_comments=review_questions_comments
                    formc.review_consent_status=review_consent_status
                    formc.review_consent_comments=review_consent_comments
                    formc.review_proposal_status=review_proposal_status
                    formc.review_proposal_comments=review_proposal_comments
                    formc.review_additional_comments=review_additional_comments
                    formc.review_recommendation=review_recommendation
                    formc.form_review_comment=form_review_comment
                    formc.form_reviewed_by=form_reviewed_by
                    formc.review_status=False
                    formc.rejected_or_accepted=False      
                    


                    try:
                        emails_of_student_and_supervisor=[]
                        emails_of_student_and_supervisor.append(formc.email_address)
                        emails_of_student_and_supervisor.append(formc.supervisor_email)
                        message=f' Form belonging to {formc.applicant_name} was sent back. Please view feedback.'
            
                        send_email(app,mail, message,emails_of_student_and_supervisor)
                    except Exception as e:
                        app.logger.error(f"Failed to send email")
                else:
                    formc.review_date1=review_date
                    formc.status=status
                    formc.review_org_permission_status1=review_org_permission_status
                    formc.review_org_permission_comments1=review_org_permission_comments
                    formc.review_waiver_status1=review_waiver_status
                    formc.form_status1=form_status
                    formc.review_waiver_comments1=review_waiver_comments
                    formc.review_form_status1=review_form_status
                    formc.review_form_comments1=review_form_comments
                    formc.review_questions_status1=review_questions_status
                    formc.review_questions_comments1=review_questions_comments
                    formc.review_consent_status1=review_consent_status
                    formc.review_consent_comments1=review_consent_comments
                    formc.review_proposal_status1=review_proposal_status
                    formc.review_proposal_comments1=review_proposal_comments
                    formc.review_additional_comments1=review_additional_comments
                    formc.review_recommendation1=review_recommendation
                    formc.form_review_comment1=form_review_comment
                    formc.form_reviewed_by1=form_reviewed_by
                    formc.review_status1=False
                    formc.rejected_or_accepted=False
                    #Uncomment the code bellow for testing
                    ##
                    


                    try:
                        emails_of_student_and_supervisor=[]
                        emails_of_student_and_supervisor.append(formc.email_address)
                        emails_of_student_and_supervisor.append(formc.supervisor_email)
                        message=f' Form belonging to {formc.applicant_name} was sent back. Please view feedback.'
            
                        send_email(app,mail, message,emails_of_student_and_supervisor)
                    except Exception as e:
                        app.logger.error(f"Failed to send email")

                #add coments to Rec table
                if user_role=='REVIEWER':
                        form=Rec(
                            rec_id=user_id,
                            form_id=id,
                            full_name=user_name.full_name,
                            rec_comments = review_additional_comments,
                            rec_status = status,
                            rec_date=datetime.now()
                            )
               
                        db_session.add(form)
            db_session.add(formc)
            db_session.commit()
            return redirect(url_for('review_dashboard'))
    
        return render_template("form_c_ethics.html",user_id=user_id,formc=formc,formReviewers=formReviewers,latest_formc=latest_formc)



@app.route('/ethics_reviewer_committee_form_a', methods=['GET','POST'])
def ethics_reviewer_committee_form_a():
    # Get year and month from query parameters
    year_param = request.args.get('year')
    month_param = request.args.get('month')
    filter_applied = request.args.get('filter_applied', 'false') == 'true'

    base_query = (
        db_session.query(FormA, FormARequirements)
        .join(User, FormA.user_id == User.user_id)
        .outerjoin(FormARequirements, FormARequirements.user_id == FormA.user_id)
    )

    latest_forma_subq = (
        db_session.query(
            FormA.user_id,
            func.max(FormA.submitted_at).label('latest_submitted_at')
        )
        .filter(FormA.submitted_at.isnot(None))
        .group_by(FormA.user_id)
        .subquery()
    )

    query = base_query.join(
        latest_forma_subq,
        and_(
            FormA.user_id == latest_forma_subq.c.user_id,
            FormA.submitted_at == latest_forma_subq.c.latest_submitted_at
        )
    )

    if not filter_applied:
        # Match chair_landing: keep forms visible after they move from admin to reviewers
        query = query.filter(
            or_(
                and_(FormA.submitted_to_admin == True, FormA.rejected_or_accepted == True),
                FormA.submitted_to_reviewers == True
            )
        )

    # Add year/month filtering after selecting the latest form per student
    if year_param and month_param:
        query = query.filter(
            extract('year', FormA.submitted_at) == int(year_param),
            func.to_char(FormA.submitted_at, 'YYYY-MM') == month_param
        )

    # Pagination
    page = request.args.get('page', default=1, type=int)
    page_size = request.args.get('page_size', default=20, type=int)
    supervisor_formA = query.order_by(FormA.submitted_at.desc()).offset((page-1)*page_size).limit(page_size).all()
   
    # Count total records for pagination controls
    total_records = query.count()
    today = date.today()
    return render_template(
        'ethics_reviewer_committee.html',
        today=today,
        submitted_form_a=supervisor_formA,
        filter_applied=filter_applied,
        page=page,
        page_size=page_size,
        total_records=total_records
    )


@app.route('/ethics_reviewer_committee_form_b', methods=['GET','POST'])
def ethics_reviewer_committee_form_b():
    # Get year and month from query parameters
    year_param = request.args.get('year')
    month_param = request.args.get('month')
    filter_applied = request.args.get('filter_applied', 'false') == 'true'
    
    # Show only the latest Form B per user (like Form A)
    base_query = db_session.query(FormB, FormARequirements)
    base_query = base_query.options(
        defer(FormB.permission_letter),
        defer(FormB.prior_clearance),
        defer(FormB.ethics_evidence),
        defer(FormB.proposal_path),
        defer(FormB.pending_note),
        defer(FormB.private_permission_file)
    ).join(User, FormB.user_id == User.user_id)
    base_query = base_query.outerjoin(FormARequirements, FormARequirements.user_id == FormB.user_id)

    # Subquery to get latest submitted_at per user
    latest_formB_subq = db_session.query(
        FormB.user_id,
        func.max(FormB.submitted_at).label('latest_submitted_at')
    )
    if filter_applied:
        latest_formB_subq = latest_formB_subq.filter(FormB.submitted_at.isnot(None))
    else:
        latest_formB_subq = latest_formB_subq.filter(
            FormB.submitted_at.isnot(None),
            or_(
                FormB.submitted_to_admin == True,
                FormB.submitted_to_reviewers == True
            )
        )
    if year_param and month_param:
        latest_formB_subq = latest_formB_subq.filter(
            extract('year', FormB.submitted_at) == int(year_param),
            func.to_char(FormB.submitted_at, 'YYYY-MM') == month_param
        )
    latest_formB_subq = latest_formB_subq.group_by(FormB.user_id).subquery()

    # Join to only get latest per user
    query = base_query.join(
        latest_formB_subq,
        (FormB.user_id == latest_formB_subq.c.user_id) & (FormB.submitted_at == latest_formB_subq.c.latest_submitted_at)
    )
    supervisor_formB = query.order_by(FormB.user_id, FormB.submitted_at.desc()).all()
    today = date.today()
    return render_template('ethics_reviewer_committee.html', today=today, submitted_form_b=supervisor_formB, filter_applied=filter_applied)


@app.route('/ethics_reviewer_committee_form_c', methods=['GET','POST'])
def ethics_reviewer_committee_form_c():
    # Get year and month from query parameters
    year_param = request.args.get('year')
    month_param = request.args.get('month')
    filter_applied = request.args.get('filter_applied', 'false') == 'true'
    
    # Show only the latest Form C per user (like Form A)
    base_query = db_session.query(FormC, FormARequirements)
    base_query = base_query.join(User, FormC.user_id == User.user_id)
    base_query = base_query.outerjoin(FormARequirements, FormARequirements.user_id == FormC.user_id)

    # Subquery to get latest submission per user
    latest_formC_subq = db_session.query(
        FormC.user_id,
        func.max(FormC.submission_date).label('latest_submission_date')
    )
    if filter_applied:
        latest_formC_subq = latest_formC_subq.filter(FormC.submission_date.isnot(None))
    else:
        latest_formC_subq = latest_formC_subq.filter(
            FormC.submission_date.isnot(None),
            or_(
                FormC.submitted_to_admin == True,
                FormC.submitted_to_reviewers == True
            )
        )
    if year_param and month_param:
        latest_formC_subq = latest_formC_subq.filter(
            extract('year', FormC.submission_date) == int(year_param),
            func.to_char(FormC.submission_date, 'YYYY-MM') == month_param
        )
    latest_formC_subq = latest_formC_subq.group_by(FormC.user_id).subquery()

    # Join to only get latest per user
    query = base_query.join(
        latest_formC_subq,
        (FormC.user_id == latest_formC_subq.c.user_id) & (FormC.submission_date == latest_formC_subq.c.latest_submission_date)
    )
    supervisor_formC = query.order_by(FormC.user_id, FormC.submission_date.desc()).all()
    today = date.today()
    return render_template('ethics_reviewer_committee.html', today=today, submitted_form_c=supervisor_formC, filter_applied=filter_applied)


@app.route('/student_form_pdf/<string:form_id>/<string:form_type>', methods=['GET','POST'])
def student_form_pdf(form_id,form_type):
    form = None
    for model in [FormA, FormB, FormC]:
        form = db_session.query(model).filter_by(form_id=form_id).first()
        if form:
            break  # Stop once the form is found
    data={}
    if form_type=='A':
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
        return render_template('student_form_a_answer_pdf.html',formA=form,data=data)
    elif form_type=='B':
        return render_template('student_form_b_answer_pdf.html',formB=form)
    elif form_type=='C':
        return render_template('student_form_c_answer_pdf.html',formc=form)

@app.route('/ethics_form_pdf/<string:form_id>/<string:form_type>', methods=['GET','POST'])
def ethics_form_pdf(form_id,form_type):
    form_type = (form_type or '').strip().upper()

    if form_type == "FORM A":
        form = db_session.query(FormA).filter_by(form_id=form_id).first()
        if not form:
            return "Form A not found.", 404

        data = {
            "org_name": parse_field(form.org_name),
            "org_contact": parse_field(form.org_contact),
            "org_role": parse_field(form.org_role),
            "org_permission": parse_field(form.org_permission),
            "fund_org": parse_field(form.fund_org),
            "fund_contact": parse_field(form.fund_contact),
            "fund_role": parse_field(form.fund_role),
            "fund_amount": parse_field(form.fund_amount),
            "population": parse_field(form.population),
            "sampling_method": parse_field(form.sampling_method),
            "sampling_size": parse_field(form.sampling_size),
            "inclusion_criteria": parse_field(form.inclusion_criteria)
        }
        return render_template('student_form_a_answer_pdf.html',formA=form,data=data)

    if form_type == "FORM B":
        form = db_session.query(FormB).filter_by(form_id=form_id).first()
        if not form:
            return "Form B not found.", 404
        return render_template('student_form_b_answer_pdf.html',formB=form)

    if form_type == "FORM C":
        form = db_session.query(FormC).filter_by(form_id=form_id).first()
        if not form:
            return "Form C not found.", 404
        return render_template('student_form_c_answer_pdf.html',formc=form)

    return "Invalid form type.", 400


@app.route('/chair_landing', methods=['POST', 'GET'])
@role_required('ADMIN', 'SUPER_ADMIN')
def chair_landing():
    

    user_id = session.get('id')
    user = db_session.query(User).filter(User.user_id == user_id).first()
    if not user:
        return redirect('/login?system=ethics')

    # Get year from query parameters
    year_param = request.args.get('year')
    year_filter = None
    try:
        if year_param:
            year_filter = int(year_param)
    except (ValueError, TypeError):
        year_filter = None

    # ---------- FORM A ----------
    latest_forma_subq = (
        db_session.query(
            FormA.user_id.label('user_id'),
            func.max(func.coalesce(FormA.submitted_at, FormA.created_at)).label('latest_date')
        )
        .group_by(FormA.user_id)
        .subquery()
    )
    formA_query = db_session.query(FormA, func.count(FormA.form_id).over(partition_by=FormA.user_id).label("total_forms"))\
        .join(
            latest_forma_subq,
            and_(
                FormA.user_id == latest_forma_subq.c.user_id,
                func.coalesce(FormA.submitted_at, FormA.created_at) == latest_forma_subq.c.latest_date
            )
        ).filter(
            or_(
                and_(FormA.submitted_to_admin == True, FormA.rejected_or_accepted == True),
                FormA.submitted_to_reviewers == True
            )
        )
    if year_filter:
        formA_query = formA_query.filter(func.extract('year', func.coalesce(FormA.submitted_at, FormA.created_at)) == year_filter)
    formAs = formA_query.order_by(FormA.user_id, func.coalesce(FormA.submitted_at, FormA.created_at).desc()).all()

    forms_by_yearA = defaultdict(lambda: defaultdict(list))
    for form, count in formAs:
        timestamp = form.submitted_at if form.submitted_at else form.created_at
        year = timestamp.year
        month = timestamp.strftime("%Y-%m")
        status = 'reviewers' if getattr(form, 'submitted_to_reviewers', False) else 'admin'
        forms_by_yearA[year][month].append((form, count, status))
    sorted_yearsA = sorted(forms_by_yearA.keys(), reverse=True)

    # ---------- FORM B ----------
    latest_formb_subq = (
        db_session.query(
            FormB.user_id.label('user_id'),
            func.max(func.coalesce(FormB.submitted_at, FormB.created_at)).label('latest_date')
        )
        .group_by(FormB.user_id)
        .subquery()
    )
    formB_query = db_session.query(FormB, func.count(FormB.form_id).over(partition_by=FormB.user_id).label("total_forms")).options(
        defer(FormB.permission_letter),
        defer(FormB.prior_clearance),
        defer(FormB.ethics_evidence),
        defer(FormB.proposal_path),
        defer(FormB.pending_note),
        defer(FormB.private_permission_file)
    ).join(
        latest_formb_subq,
        and_(
            FormB.user_id == latest_formb_subq.c.user_id,
            func.coalesce(FormB.submitted_at, FormB.created_at) == latest_formb_subq.c.latest_date
        )
    ).filter(
        or_(
            and_(FormB.submitted_to_admin == True),
            FormB.submitted_to_reviewers == True
        )
    )
    if year_filter:
        formB_query = formB_query.filter(func.extract('year', func.coalesce(FormB.submitted_at, FormB.created_at)) == year_filter)
    formBs = formB_query.order_by(FormB.user_id, func.coalesce(FormB.submitted_at, FormB.created_at).desc()).all()

    forms_by_yearB = defaultdict(lambda: defaultdict(list))
    for form, count in formBs:
        timestamp = form.submitted_at if form.submitted_at else form.created_at
        year = timestamp.year
        month = timestamp.strftime("%Y-%m")
        status = 'reviewers' if getattr(form, 'submitted_to_reviewers', False) else 'admin'
        forms_by_yearB[year][month].append((form, count, status))
    sorted_yearsB = sorted(forms_by_yearB.keys(), reverse=True)

    # ---------- FORM C ----------
    latest_formc_subq = (
        db_session.query(
            FormC.user_id.label('user_id'),
            func.max(func.coalesce(FormC.submission_date, FormC.created_at)).label('latest_date')
        )
        .group_by(FormC.user_id)
        .subquery()
    )
    formC_query = db_session.query(FormC, func.count(FormC.form_id).over(partition_by=FormC.user_id).label("total_forms"))\
        .join(
            latest_formc_subq,
            and_(
                FormC.user_id == latest_formc_subq.c.user_id,
                func.coalesce(FormC.submission_date, FormC.created_at) == latest_formc_subq.c.latest_date
            )
        ).filter(
            or_(
                and_(FormC.submitted_to_admin == True),
                FormC.submitted_to_reviewers == True
            )
        )
    if year_filter:
        formC_query = formC_query.filter(func.extract('year', func.coalesce(FormC.submission_date, FormC.created_at)) == year_filter)
    formCs = formC_query.order_by(FormC.user_id, func.coalesce(FormC.submission_date, FormC.created_at).desc()).all()

    forms_by_yearC = defaultdict(lambda: defaultdict(list))
    for form, count in formCs:
        timestamp = form.submission_date if form.submission_date else form.created_at
        year = timestamp.year
        month = timestamp.strftime("%Y-%m")
        status = 'reviewers' if getattr(form, 'submitted_to_reviewers', False) else 'admin'
        forms_by_yearC[year][month].append((form, count, status))
    sorted_yearsC = sorted(forms_by_yearC.keys(), reverse=True)

    role = user.role.value if user and user.role else None
    return render_template(
        "chair-landing-dashboard.html",
        role=role,
        forms_by_yearA=forms_by_yearA,
        sorted_yearsA=sorted_yearsA,
        forms_by_yearB=forms_by_yearB,
        sorted_yearsB=sorted_yearsB,
        forms_by_yearC=forms_by_yearC,
        sorted_yearsC=sorted_yearsC,
        current_year=datetime.now().year
    )


@app.route('/admin/login_logs', methods=['GET'])
def admin_login_logs():
    user_id = session.get('id')
    if not user_id:
        return redirect('/login?system=ethics')

    current_user = db_session.query(User).filter(User.user_id == user_id).first()
    if not current_user or not current_user.role or current_user.role.value not in ['ADMIN', 'SUPER_ADMIN']:
        flash('You are not authorized to view login logs.', 'danger')
        return redirect('/login?system=ethics')

    user_search = (request.args.get('search') or request.args.get('email') or '').strip()
    start_date_raw = (request.args.get('start_date') or '').strip()
    end_date_raw = (request.args.get('end_date') or '').strip()

    # --- Pagination parameters ---
    iu_page = int(request.args.get('iu_page', 1))
    iu_per_page = int(request.args.get('iu_per_page', 20))
    log_page = int(request.args.get('log_page', 1))
    log_per_page = int(request.args.get('log_per_page', 20))
    iu_inactive_only = request.args.get('iu_inactive_only', '0') == '1'
    iu_years = request.args.get('iu_years', '')
    try:
        iu_years = int(iu_years)
    except (ValueError, TypeError):
        iu_years = None

    # --- Inactive Users Table Data ---
    all_users = db_session.query(User).order_by(User.full_name.asc()).all()
    user_name_suggestions = sorted({
        user.full_name for user in all_users if user.full_name
    }, key=lambda name: name.casefold())

    def matches_user_search(user):
        if not user_search:
            return True
        search_value = user_search.casefold()
        return any(
            search_value in str(value).casefold()
            for value in [
                getattr(user, 'full_name', None),
                getattr(user, 'email', None),
                getattr(user, 'student_number', None),
                getattr(user, 'staff_number', None),
                getattr(user, 'user_id', None),
            ]
            if value
        )

    subq = (
        db_session.query(
            UserActivityLog.user_id,
            func.max(UserActivityLog.timestamp).label('last_login')
        )
        .filter(UserActivityLog.action == 'login')
        .group_by(UserActivityLog.user_id)
        .subquery()
    )
    user_last_logins = dict(
        db_session.query(subq.c.user_id, subq.c.last_login)
    )
    now = datetime.now(timezone.utc)
    inactive_users = []
    for user in all_users:
        if not matches_user_search(user):
            continue
        last_login = user_last_logins.get(user.user_id)
        if last_login:
            delta = now - last_login
            days = delta.days
            if days < 1:
                inactivity = f"<1 day"
            elif days < 7:
                inactivity = f"{days} day{'s' if days > 1 else ''}"
            elif days < 365:
                inactivity = f"{days // 7} week{'s' if days // 7 > 1 else ''}"
            else:
                inactivity = f"{days // 365} year{'s' if days // 365 > 1 else ''}"
        else:
            last_login = None
            inactivity = "Never logged in"
        # Determine if user is active based on authenticate_student
        is_active = (str(user.authenticate_student).lower() == 'true')
        # Filtering logic
        show = True
        if iu_inactive_only:
            # Only show users who have never logged in or last login > 30 days ago
            if last_login:
                show = (now - last_login).days > 30
            else:
                show = True
        if iu_years is not None:
            # Only show users who have not logged in for at least iu_years
            if last_login:
                show = show and ((now - last_login).days >= iu_years * 365)
            else:
                show = show and True
        if show:
            inactive_users.append({
                'user': user,
                'last_login': last_login,
                'inactivity': inactivity,
                'is_active': is_active
            })
    inactive_users.sort(key=lambda x: (x['last_login'] is not None, x['last_login'] or datetime(1900,1,1)), reverse=False)
    iu_total = len(inactive_users)
    iu_pages = max(1, (iu_total + iu_per_page - 1) // iu_per_page)
    iu_start = (iu_page - 1) * iu_per_page
    iu_end = iu_start + iu_per_page
    inactive_users_paginated = inactive_users[iu_start:iu_end]

    # --- Existing login log table ---
    query = (
        db_session.query(UserActivityLog, User)
        .join(User, UserActivityLog.user_id == User.user_id)
        .filter(UserActivityLog.action == 'login')
    )
    if user_search:
        search_term = f"%{user_search}%"
        query = query.filter(
            or_(
                User.full_name.ilike(search_term),
                User.email.ilike(search_term),
                cast(User.student_number, String).ilike(search_term),
                cast(User.staff_number, String).ilike(search_term),
                User.user_id.ilike(search_term),
            )
        )
    if start_date_raw:
        try:
            start_dt = parse_admin_log_date(start_date_raw)
            query = query.filter(UserActivityLog.timestamp >= start_dt)
        except ValueError:
            flash('Invalid start date format. Please use dd/mm/yyyy or YYYY-MM-DD.', 'warning')
    if end_date_raw:
        try:
            end_dt = parse_admin_log_date(end_date_raw)
            end_dt = datetime.combine(end_dt.date(), dt_time.max)
            query = query.filter(UserActivityLog.timestamp <= end_dt)
        except ValueError:
            flash('Invalid end date format. Please use dd/mm/yyyy or YYYY-MM-DD.', 'warning')
    log_total = query.count()
    log_pages = max(1, (log_total + log_per_page - 1) // log_per_page)
    log_rows = (
        query
        .order_by(UserActivityLog.timestamp.desc())
        .offset((log_page - 1) * log_per_page)
        .limit(log_per_page)
        .all()
    )
    # --- User Activity Logs Table ---

    from sqlalchemy.orm import aliased
    TargetUser = aliased(User)
    activity_page = int(request.args.get('activity_page', 1))
    activity_per_page = int(request.args.get('activity_per_page', 20))
    activity_query = (
        db_session.query(UserActivityLog, User, TargetUser)
        .join(User, UserActivityLog.user_id == User.user_id)
        .outerjoin(TargetUser, UserActivityLog.target_user_id == TargetUser.user_id)
        .order_by(UserActivityLog.timestamp.desc())
    )
    if user_search:
        search_term = f"%{user_search}%"
        activity_query = activity_query.filter(
            or_(
                User.full_name.ilike(search_term),
                User.email.ilike(search_term),
                cast(User.student_number, String).ilike(search_term),
                cast(User.staff_number, String).ilike(search_term),
                User.user_id.ilike(search_term),
                TargetUser.full_name.ilike(search_term),
                TargetUser.email.ilike(search_term),
                cast(TargetUser.student_number, String).ilike(search_term),
                cast(TargetUser.staff_number, String).ilike(search_term),
                TargetUser.user_id.ilike(search_term),
            )
        )
    activity_total = activity_query.count()
    activity_pages = max(1, (activity_total + activity_per_page - 1) // activity_per_page)
    activity_rows = (
        activity_query
        .offset((activity_page - 1) * activity_per_page)
        .limit(activity_per_page)
        .all()
    )

    role = current_user.role.value if current_user and current_user.role else None
    return render_template(
        'admin_login_logs.html',
        role=role,
        log_rows=log_rows,
        log_page=log_page,
        log_pages=log_pages,
        log_per_page=log_per_page,
        log_total=log_total,
        inactive_users=inactive_users_paginated,
        iu_page=iu_page,
        iu_pages=iu_pages,
        iu_per_page=iu_per_page,
        iu_total=iu_total,
        iu_inactive_only=iu_inactive_only,
        iu_years=request.args.get('iu_years', ''),
        activity_rows=activity_rows,
        activity_page=activity_page,
        activity_pages=activity_pages,
        activity_per_page=activity_per_page,
        activity_total=activity_total,
        user_name_suggestions=user_name_suggestions,
        filters={
            'search': user_search,
            'email': user_search,
            'start_date': start_date_raw,
            'end_date': end_date_raw,
        }
    )


@app.route('/api/admin/login_logs', methods=['GET'])
def api_admin_login_logs():
    user_id = session.get('id')
    if not user_id:
        return jsonify({'message': 'Unauthorized'}), 401

    current_user = db_session.query(User).filter(User.user_id == user_id).first()
    if not current_user or not current_user.role or current_user.role.value not in ['ADMIN', 'SUPER_ADMIN']:
        return jsonify({'message': 'Forbidden'}), 403

    email_filter = (request.args.get('email') or '').strip()
    start_date_raw = (request.args.get('start_date') or '').strip()
    end_date_raw = (request.args.get('end_date') or '').strip()
    limit_raw = (request.args.get('limit') or '200').strip()

    try:
        limit = int(limit_raw)
    except ValueError:
        limit = 200
    limit = max(1, min(limit, 1000))

    query = (
        db_session.query(UserActivityLog, User)
        .join(User, UserActivityLog.user_id == User.user_id)
        .filter(UserActivityLog.action == 'login')
    )

    if email_filter:
        query = query.filter(User.email.ilike(f"%{email_filter}%"))

    if start_date_raw:
        try:
            start_dt = datetime.fromisoformat(start_date_raw)
            query = query.filter(UserActivityLog.timestamp >= start_dt)
        except ValueError:
            return jsonify({'message': 'Invalid start_date. Use YYYY-MM-DD.'}), 400

    if end_date_raw:
        try:
            end_dt = datetime.fromisoformat(end_date_raw)
            end_dt = datetime.combine(end_dt.date(), dt_time.max)
            query = query.filter(UserActivityLog.timestamp <= end_dt)
        except ValueError:
            return jsonify({'message': 'Invalid end_date. Use YYYY-MM-DD.'}), 400

    rows = (
        query
        .order_by(UserActivityLog.timestamp.desc())
        .limit(limit)
        .all()
    )

    data = [
        {
            'activity_id': log.activity_id,
            'user_id': user.user_id,
            'full_name': user.full_name,
            'email': user.email,
            'role': user.role.value if user.role else None,
            'login_at': log.timestamp.isoformat() if log.timestamp else None,
        }
        for log, user in rows
    ]

    return jsonify({'count': len(data), 'data': data}), 200


@app.route('/review_version/<string:user_id>/<string:form_name>', methods=['GET','POST'])
def review_version(user_id,form_name):
    
    form = None
    for model in [FormA, FormB, FormC]:
        query = (
            db_session.query(model, FormARequirements)
            .outerjoin(FormARequirements, FormARequirements.user_id == model.user_id)
            .filter(model.user_id == user_id)
        )
        
        # Add defer options for FormB binary columns
        if model == FormB:
            query = query.options(
                defer(FormB.permission_letter),
                defer(FormB.prior_clearance),
                defer(FormB.ethics_evidence),
                defer(FormB.proposal_path),
                defer(FormB.pending_note),
                defer(FormB.private_permission_file)
            )

        # Pick the correct date field for ordering
        if hasattr(model, "submitted_at"):
            query = query.order_by(model.submitted_at.desc())
        elif hasattr(model, "submission_date"):
            query = query.order_by(model.submission_date.desc())

        form = query.all()

        if form:
            break  # Stop once the form is found

   
    user_id=session.get('id')
    return render_template('review_version.html',form=form,form_name=form_name,user_id=user_id)


@app.route('/review_dashboard', methods=['GET','POST'])
def review_dashboard():
    user_id=session.get('id')

    latest_form_a_subq = (
        db_session.query(
            FormA.user_id.label('user_id'),
            func.max(FormA.submitted_at).label('latest_submitted_at')
        )
        .filter(FormA.submitted_at.isnot(None))
        .group_by(FormA.user_id)
        .subquery()
    )

    submitted_form_a = (
        db_session.query(FormA, FormARequirements)
        .join(
            latest_form_a_subq,
            and_(
                FormA.user_id == latest_form_a_subq.c.user_id,
                FormA.submitted_at == latest_form_a_subq.c.latest_submitted_at
            )
        )
        .join(User, FormA.user_id == User.user_id)
        .outerjoin(FormARequirements, FormARequirements.user_id == FormA.user_id)
        .filter(
            or_(
                FormA.reviewer_name1 == user_id,
                FormA.reviewer_name2 == user_id
            )
        )
        .order_by(FormA.submitted_at.desc())
        .all()
    )
    form_aa=[]
    form_bb=[]
    form_cc=[]
    if submitted_form_a:
        
        for form_a, requirementsa in submitted_form_a:
        
            form_aa.append(
                {"forma":form_a,
                 "requirementsa":requirementsa})
            
         
    else:
        form_a, requirementsa = None, None
   
    latest_form_b_subq = (
        db_session.query(
            FormB.user_id.label('user_id'),
            func.max(FormB.submitted_at).label('latest_submitted_at')
        )
        .filter(FormB.submitted_at.isnot(None))
        .group_by(FormB.user_id)
        .subquery()
    )

    submitted_form_b = (
        db_session.query(FormB, FormARequirements)
        .join(
            latest_form_b_subq,
            and_(
                FormB.user_id == latest_form_b_subq.c.user_id,
                FormB.submitted_at == latest_form_b_subq.c.latest_submitted_at
            )
        )
        .join(User, FormB.user_id == User.user_id)
        .outerjoin(FormARequirements, FormARequirements.user_id == FormB.user_id)
        .filter(
            or_(
                FormB.reviewer_name1 == user_id,
                FormB.reviewer_name2 == user_id
            )
        )
        .order_by(FormB.submitted_at.desc())
        .all()
    )

    if submitted_form_b:
        for form_b, requirementsb in submitted_form_b:

            form_bb.append(
                {"formb":form_b,
                 "requirementsb":requirementsb})
            
            
    else:
        form_b, requirementsb = None, None
    # Form C
    latest_form_c_subq = (
        db_session.query(
            FormC.user_id.label('user_id'),
            func.max(FormC.submission_date).label('latest_submission_date')
        )
        .filter(FormC.submission_date.isnot(None))
        .group_by(FormC.user_id)
        .subquery()
    )

    submitted_form_c = (
        db_session.query(FormC, FormARequirements)
        .join(
            latest_form_c_subq,
            and_(
                FormC.user_id == latest_form_c_subq.c.user_id,
                FormC.submission_date == latest_form_c_subq.c.latest_submission_date
            )
        )
        .join(User, FormC.user_id == User.user_id)
        .outerjoin(FormARequirements, FormARequirements.user_id == FormC.user_id)
        .filter(
            or_(
                FormC.reviewer_name1 == user_id,
                FormC.reviewer_name2 == user_id
            )
        )
        .order_by(FormC.submission_date.desc())
        .all()
    )

    if submitted_form_c:
        for form_c, requirementsc in submitted_form_c:
        
            form_cc.append(
                {"formc":form_c,
                 "requirementsc":requirementsc})
    else:
        form_c, requirementsc = None, None
   
    today = date.today()
   
    return render_template('review-dashboard.html',
                user_id=user_id,today=today,
                submitted_form_a=form_aa,
                submitted_form_b=form_bb,
                submitted_form_c=form_cc)



@app.route('/submit_to_rec/<string:id>', methods=['GET'])
def submit_to_rec(id):
   
    form = None
    for model in [FormA, FormB, FormC]:
        form = db_session.query(model).filter_by(form_id=id).first()
        if form:
            break  # Stop once the form is found
    
    if form:
        form.submitted_to_rec=True
        db_session.commit()
    return redirect(url_for('chair_landing'))
    


@app.route('/reviewer_form_a/<string:id>', methods=['GET'])
def reviewer_form_a(id):
    form = db_session.query(FormA).filter_by(form_id=id).first()
    data={}
    if form:
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

    if form:
        return render_template("review_form_a.html", form=form,data=data)
    else:
        # You can pass an error message or just load the dashboard
        return redirect(url_for('review_dashboard'))


@app.route('/reviewer_form_b/<string:id>', methods=['GET'])
def reviewer_form_b(id):
   
    form = db_session.query(FormB).options(
        defer(FormB.permission_letter),
        defer(FormB.prior_clearance),
        defer(FormB.ethics_evidence),
        defer(FormB.proposal_path),
        defer(FormB.pending_note),
        defer(FormB.private_permission_file)
    ).filter_by(form_id=id).first()

    if form:
        return render_template("review_form_b.html",form=form)
    else:
        # You can pass an error message or just load the dashboard
        return redirect(url_for('review_dashboard'))



@app.route('/reviewer_form_c/<string:id>', methods=['GET'])
def reviewer_form_c(id):
    form = db_session.query(FormC).filter_by(form_id=id).first()
   
    if form:
        return render_template("review_form_c.html", form=form)
    else:
        # You can pass an error message or just load the dashboard
        return redirect(url_for('review_dashboard'))
    


@app.route('/rec_dashboard', methods=['GET', 'POST'])
def rec_dashboard():
    user_id = session.get('id')
    if not user_id:
        return redirect('/login?system=ethics')

    user = db_session.query(User).filter(User.user_id == user_id).first()
    if not user:
        return redirect('/login?system=ethics')
    
    
    today = date.today()
    role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    # Count reviews per form_id
    form_review_counts = dict(
        db_session.query(Rec.form_id, func.count(Rec.rec_id))
        .group_by(Rec.form_id)
        .all()
    )

    


    # Shared filter conditions
    def get_common_filters(FormModel):
        return [
            FormModel.rejected_or_accepted == True,
            FormModel.review_signature_date != None,
            ~func.lower(FormModel.risk_level if hasattr(FormModel, 'risk_level') else FormModel.risk_rating).like('%low%'),
            FormModel.review_status == True,
            FormModel.review_status1 == True,
            FormModel.submitted_to_rec == True,
            FormModel.reviewer_name1 != user_id,
            FormModel.reviewer_name2 != user_id,
        ]

    # Form A
    submitted_form_a = [
        (form, req, form_review_counts.get(form.form_id, 0))
        for form, req in db_session.query(FormA, FormARequirements)
            .outerjoin(FormARequirements, FormA.user_id == FormARequirements.user_id)
            .outerjoin(Rec, Rec.form_id == FormA.form_id)
            .filter(*get_common_filters(FormA))
            .all()
    ]

    # Form B
    submitted_form_b = [
        (form, req, form_review_counts.get(form.form_id, 0))
        for form, req in db_session.query(FormB, FormARequirements)
            .options(
                defer(FormB.permission_letter),
                defer(FormB.prior_clearance),
                defer(FormB.ethics_evidence),
                defer(FormB.proposal_path),
                defer(FormB.pending_note),
                defer(FormB.private_permission_file)
            )
            .outerjoin(FormARequirements, FormB.user_id == FormARequirements.user_id)
            .outerjoin(Rec, Rec.form_id == FormB.form_id)
            .filter(*get_common_filters(FormB))
            .all()
    ]

    # Form C
    submitted_form_c = [
        (form, req, form_review_counts.get(form.form_id, 0))
        for form, req in db_session.query(FormC, FormARequirements)
            .outerjoin(FormARequirements, FormC.user_id == FormARequirements.user_id)
            .outerjoin(Rec, Rec.form_id == FormC.form_id)
            .filter(*get_common_filters(FormC))
            .all()
    ]

    # Count all reviewers
    all_reviewers_counter = db_session.query(User).filter(User.role == 'REVIEWER').count()

    # Supervisor-specific requirements
    supervisor_formA_req = db_session.query(FormARequirements).filter_by(user_id=user_id).all()

    return render_template(
        'rec-dashboard.html',
        today=today,
        role=role,
        all_Reviewers_counter=all_reviewers_counter,
        submitted_form_a=submitted_form_a,
        submitted_form_b=submitted_form_b,
        submitted_form_c=submitted_form_c,
        supervisor_formA_req=supervisor_formA_req
        
    )


@app.route('/admin_rec_form/<string:form_id>',methods=['GET','POST'])
def admin_rec_form(form_id):
  
    user_id = session.get('id')
    if not user_id:
        return redirect('/login?system=ethics')

    user=db_session.query(User).filter(User.user_id==user_id).first()
    if not user:
        return redirect('/login?system=ethics')

    form = None
    Rec_team = db_session.query(Rec).filter(Rec.form_id == form_id).all()
    for model in [FormA, FormB, FormC]:
        form = db_session.query(model).filter_by(form_id=form_id).first()
        if form:
            break  # Stop once the form is found

    role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    if not form:
        return redirect(url_for('rec_dashboard'))
    # Count unique reviewers for this form
    unique_reviewer_ids = set()
    unique_reviewer_names = set()
    for rec in Rec_team:
        if rec.rec_id:
            unique_reviewer_ids.add(rec.rec_id)
        if rec.full_name:
            unique_reviewer_names.add(rec.full_name)
    unique_reviewer_count = len(unique_reviewer_ids)

    # Get all reviewers in the system
    all_reviewers = db_session.query(User).filter(User.role == 'REVIEWER').all()
    all_reviewer_ids = set([r.user_id for r in all_reviewers])
    all_reviewer_names = set([r.full_name for r in all_reviewers])

    # Reviewers who have not yet reviewed this form
    not_reviewed_ids = all_reviewer_ids - unique_reviewer_ids
    not_reviewed_names = all_reviewer_names - unique_reviewer_names

    all_reviewers_counter = len(all_reviewers)

    return render_template(
        'chair_rec_form.html',
        Rec_team=Rec_team,
        role=role,
        form=form,
        all_reviewers_counter=all_reviewers_counter,
        unique_reviewer_count=unique_reviewer_count,
        unique_reviewer_names=list(unique_reviewer_names),
        not_reviewed_ids=list(not_reviewed_ids),
        not_reviewed_names=list(not_reviewed_names)
    )
@app.route('/rec_form_a/<string:id>', methods=['GET'])
def rec_form_a(id):
    
    form = db_session.query(FormA).filter(FormA.form_id==id).first()
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
    if form:
        return render_template("rec_form_a.html", form=form,data=data)
    else:
        # You can pass an error message or just load the dashboard
        return redirect(url_for('rec_dashboard'))


@app.route('/rec_form_b/<string:id>', methods=['GET'])
def rec_form_b(id):
   
    form = db_session.query(FormB).options(
        defer(FormB.permission_letter),
        defer(FormB.prior_clearance),
        defer(FormB.ethics_evidence),
        defer(FormB.proposal_path),
        defer(FormB.pending_note),
        defer(FormB.private_permission_file)
    ).filter(FormB.form_id==id).first()

    if form:
        return render_template("rec_form_b.html",form=form)
    else:
        # You can pass an error message or just load the dashboard
        return redirect(url_for('rec_dashboard'))



@app.route('/rec_form_c/<string:id>', methods=['GET'])
def rec_form_c(id):
    form = db_session.query(FormC).filter(FormC.form_id==id).first()
   
    if form:
        return render_template("rec_form_c.html", form=form)
    else:
        # You can pass an error message or just load the dashboard
        return redirect(url_for('rec_dashboard'))
    


@app.route('/rec_response/<string:id>', methods=['GET', 'POST'])
def rec_response(id):
    user_id=session.get('id')
    if request.method == 'POST':
        status = request.form.get('status')
        comments = request.form.get('rec_comments')  # âœ… corrected from 'additional_comments'

        # Loop through models to find the correct form by ID
        
        user_name=db_session.query(User).filter_by(user_id=user_id).first()
       
        form=Rec(
                rec_id=user_id,
                form_id=id,
                full_name=user_name.full_name,
                rec_comments = comments,
                rec_status = status,
                rec_date=datetime.now()
                )
        db_session.add(form)
        db_session.commit()
        flash("Form updated successfully", "success")

        return redirect(url_for('rec_dashboard'))

    return "Invalid access", 405



def generate_clearance_code(committee_acronym, decision_date=None):
    if decision_date is None:
        decision_date = datetime.today()

    # Format the date as YYYYMMDD
    date_str = decision_date.strftime('%Y%m%d')

    total_count = 0  # Initialize total decision count

    for model in [FormA, FormB, FormC]:
        count = (
            db_session.query(func.count())
            .select_from(model)
            .filter(cast(model.rec_date, Date) == decision_date.date())
            .scalar()
        )
        total_count += count
    
    # Increment for the new decision
    decision_number = total_count + 1
    
    # Format the final clearance code
    clearance_code = f"{committee_acronym}{date_str}{decision_number:02d}"
    return clearance_code


@app.route('/certificate/<string:id>', methods=['GET', 'POST'])
def certificate(id):
    code = 'JBSREC'
    certification_code = generate_clearance_code(code)

    certificate_details = None
    for model in [FormA, FormB, FormC]:
        certificate_details = db_session.query(model).filter_by(form_id=id).first()
        if certificate_details:
            

            if request.method == 'POST':
                certificate_details.certificate_code = certification_code
                
                certificate_details.certificate_issued = datetime.now()
                certificate_details.certificate_valid_years = int(request.form.get('valid_years'))
                certificate_details.certificate_end_date = request.form.get('end_date')
                certificate_details.certificate_issuer = request.form.get('certificate_issuer')
                certificate_details.certificate_email = request.form.get('email')
                
            
                # Overwrite with provided issued date if present
                issued_date = request.form.get('certificate_issued')
                if issued_date:
                    certificate_details.certificate_issued = datetime.now()
            
            db_session.add(certificate_details)
            db_session.commit()
            
            break

    if not certificate_details:
        return "No certificate data found.", 404
    
    return render_template(
        'certificate.html',
        certificate_details=certificate_details,
        certification_code=certificate_details.certificate_code
    )



@app.route('/modify_certificate/<string:id>', methods=['GET', 'POST'])
def modify_certificate(id):
    code = 'JBSREC'
    
    certificate_details = None
    for model in [FormA, FormB, FormC]:
        certificate_details = db_session.query(model).filter_by(form_id=id).first()
        if certificate_details:
            

            if request.method == 'POST':
                
                
                certificate_details.certificate_issued = datetime.now()
                certificate_details.certificate_valid_years = int(request.form.get('valid_years'))
                certificate_details.certificate_end_date = request.form.get('end_date')
                certificate_details.certificate_issuer = request.form.get('certificate_issuer')
                certificate_details.certificate_email = request.form.get('email')
                # Collect condition items, trim whitespace and ignore empty entries
                conditions = [c.strip() for c in request.form.getlist('conditions[]') if c and c.strip()]
                # Store conditions as a JSON array string to avoid ambiguous splitting on commas
                try:
                    heading = json.dumps(conditions)
                except Exception:
                    # Fallback to join with comma if JSON serialization fails
                    heading = ",".join(conditions)
                certificate_details.certificate_heading = heading if heading else None
                certificate_details.certificate_modified=True
                certificate_details.certificate_received=False
                # Overwrite with provided issued date if present
                issued_date = request.form.get('certificate_issued')
                if issued_date:
                    certificate_details.certificate_issued = datetime.now()
            
            db_session.add(certificate_details)
            db_session.commit()
            
            break

    if not certificate_details:
        return "No certificate data found.", 404
    
    return render_template(
        'edit_certificate.html',
        certificate_details=certificate_details
        
    )


@app.route('/view_certificate/<string:id>',methods=['GET','POST'])
def view_certificate(id):
    
    certificate_details = None
    for model in [FormA, FormB, FormC]:
        certificate_details = db_session.query(model).filter_by(form_id=id).first()
        if certificate_details:
            break
    return render_template(
        'view_certificate.html',
        certificate_details=certificate_details
    )


@app.route('/edited_certificate/<string:id>', methods=['GET'])
def edited_certificate(id):
    certificate_details = None
    for model in [FormA, FormB, FormC]:
        certificate_details = db_session.query(model).filter_by(form_id=id).first()
        if certificate_details:
            break
    if not certificate_details:
        return "No certificate data found.", 404
    return render_template('edited_certificate.html', certificate_details=certificate_details)



###
### Admin Review Submision
###
@app.route('/ethics_reviewer_committee_forms/<string:id>/<string:form_name>', methods=['GET','POST'])
def ethics_reviewer_committee_forms(id,form_name):
    def resolve_reviewer_ids(selected_reviewers, existing_reviewer_ids):
        unique_selected = []
        for reviewer_id in selected_reviewers or []:
            reviewer_id = (reviewer_id or '').strip()
            if reviewer_id and reviewer_id not in unique_selected:
                unique_selected.append(reviewer_id)
        if unique_selected:
            return unique_selected[:2]
        return (existing_reviewer_ids or [])[:2]

    forma = db_session.query(FormA).filter_by(form_id=id).first()
    
    Assigned_reviewer=''
    if forma:
        id_of_reviewers = get_reviewers_for_ethics_assignment(forma, FormA, FormA.submitted_at)
        if id_of_reviewers:
            Assigned_reviewer = db_session.query(User).filter(User.user_id.in_(id_of_reviewers)).all()
 
    list_of_revewers=[]
    id_of_reviewers=[]
    if Assigned_reviewer:
        for item in Assigned_reviewer:
            id_of_reviewers.append(item.user_id)
            list_of_revewers.append(item.email)
    else:
        reviewers=request.form.getlist('reviewer_names[]')

        if len(reviewers) >= 2:
            Assigned_reviewer=db_session.query(User).filter(User.user_id.in_([reviewers[0], reviewers[1]])).all()
            

    if form_name=="FORM A":
        
        if request.method=="POST":
            reviewers=request.form.getlist('reviewer_names[]')
            if request.form.get('accept') in ['Accept','Approved with Minor Changes'] and len(reviewers) > 2:
                flash('Please select no more than two reviewers before submitting.', 'danger')
                return redirect(url_for('ethics_reviewer_committee_forms', id=id, form_name=form_name))

            effective_reviewer_ids = resolve_reviewer_ids(reviewers, id_of_reviewers)
            if request.form.get('accept') in ['Accept','Approved with Minor Changes'] and len(effective_reviewer_ids) < 1:
                flash('Please assign at least one reviewer before submitting.', 'danger')
                return redirect(url_for('ethics_reviewer_committee_forms', id=id, form_name=form_name))

            _reviewers_emails=[]
            if reviewers:
                _reviewers_emails=db_session.query(User).filter(User.user_id.in_(effective_reviewer_ids)).all()

            forma.reviewer_name1 = effective_reviewer_ids[0] if len(effective_reviewer_ids) >= 1 else None
            forma.reviewer_name2 = effective_reviewer_ids[1] if len(effective_reviewer_ids) >= 2 else None
            forma.ethics_supervisor_signature_date=datetime.now()
            forma.review_form_comments=request.form.get('additional_comments')
            forma.ethics_supervisor_form_status=request.form.get('recommendation')
            if request.form.get('accept') in ['Accept','Approved with Minor Changes']:
                if Assigned_reviewer:
                    #Uncomment the code bellow for testing
                    ##
                    for item in Assigned_reviewer:
                        list_of_revewers.append(item.email)
                    
                    try:
                        message=f' You are assigned as a reviewer for a form belonging to {forma.applicant_name}. Please log into the ethics application system and review the form.' 

                        send_email(app,mail, message,list_of_revewers)
                    except Exception as e:
                        print(f"Error sending email: {e}")  
                
                elif _reviewers_emails:
                    for item in _reviewers_emails:
                        list_of_revewers.append(item.email)
                    try:
                        message=f' You are assigned as a reviewer for a form belonging to {forma.applicant_name}. Please log into the ethics application system and review the form.' 

                        send_email(app,mail, message,list_of_revewers)
                    except Exception as e:
                        print(f"Error sending email: {e}")
                else:
                    #Uncomment the code bellow for testing
                    ##
                    
                    try:
                        message=f'You are assigned as a reviewer for a form belonging to {forma.applicant_name}. Please log into the ethics application system and review the form.' 

                        send_email(app,mail, message,list_of_revewers)
                    except Exception as e:
                        print(f"Error sending email: {e}")  
                forma.rejected_or_accepted=True
                forma.submitted_to_reviewers=True
                # Log admin action for FormA
                db_session.add(UserActivityLog(
                    user_id=session.get('id'),
                    action='assign_reviewers',
                    page='FORM A Ethics Assignment',
                    target_user_id=forma.user_id,
                    details=f"Assigned reviewers: {forma.reviewer_name1}, {forma.reviewer_name2} to FORM A for {forma.applicant_name}"
                ))
            else:
                forma.submitted_to_reviewers=False
                forma.rejected_or_accepted=False
                emails=[]
                emails.append(forma.email)
                emails.append(forma.supervisor_email)
                try:
                    message=f' Form belonging to {forma.applicant_name} was sent back. Please view feedback.' 
            
                    send_email(app,mail, message,emails)
                except Exception as e:
                    app.logger.error(f"Failed to send email")
            db_session.add(forma)
            db_session.commit()
            return redirect(url_for('chair_landing'))
        return render_template("form_a_ethics.html",formA=forma)
    elif form_name=="FORM B":
        formb = db_session.query(FormB).filter_by(form_id=id).first()
        Assigned_reviewer=''
        if formb:
            id_of_reviewers = get_reviewers_for_ethics_assignment(formb, FormB, FormB.submitted_at)
            if id_of_reviewers:
                Assigned_reviewer = db_session.query(User).filter(User.user_id.in_(id_of_reviewers)).all()
 
        list_of_revewers=[]
        id_of_reviewers=[]
        if Assigned_reviewer:
            for item in Assigned_reviewer:
                id_of_reviewers.append(item.user_id)
                list_of_revewers.append(item.email)
        else:
            reviewers=request.form.getlist('reviewer_names[]')
            
            if len(reviewers) >= 2:
                Assigned_reviewer=db_session.query(User).filter(User.user_id.in_([reviewers[0], reviewers[1]])).all()
  
        if request.method=="POST":
            reviewers=request.form.getlist('reviewer_names[]')
            if request.form.get('accept') in ['Accept','Approved with Minor Changes'] and len(reviewers) > 2:
                flash('Please select no more than two reviewers before submitting.', 'danger')
                return redirect(url_for('ethics_reviewer_committee_forms', id=id, form_name=form_name))

            effective_reviewer_ids = resolve_reviewer_ids(reviewers, id_of_reviewers)
            if request.form.get('accept') in ['Accept','Approved with Minor Changes'] and len(effective_reviewer_ids) < 1:
                flash('Please assign at least one reviewer before submitting.', 'danger')
                return redirect(url_for('ethics_reviewer_committee_forms', id=id, form_name=form_name))

            formb.reviewer_name1 = effective_reviewer_ids[0] if len(effective_reviewer_ids) >= 1 else None
            formb.reviewer_name2 = effective_reviewer_ids[1] if len(effective_reviewer_ids) >= 2 else None
            formb.ethics_supervisor_signature_date=datetime.now()
            formb.review_form_comments=request.form.get('additional_comments')
            formb.ethics_supervisor_form_status=request.form.get('recommendation')
            
            if request.form.get('accept') in ['Accept','Approved with Minor Changes']:
                if Assigned_reviewer:
                    for item in Assigned_reviewer:
                        list_of_revewers.append(item.email)
                    
                    #Uncomment the code bellow for testing
                    ##
                   
                    try:
                        message=f' You areassigned as a reviewer for a form belonging to {formb.applicant_name}. Please log into the ethics application system and review the form' 

                        send_email(app,mail, message,list_of_revewers)
                    except Exception as e:
                        print(f"Error sending email: {e}")  

                else:
                    #Uncomment the code bellow for testing
                    ##
                    try:
                        message=f'You areassigned as a reviewer for a form belonging to {formb.applicant_name}. Please log into the ethics application system and review the form' 
            
                        send_email(app,mail, message,list_of_revewers)
                    except Exception as e:
                        print(f"Error sending email: {e}")
                formb.rejected_or_accepted=True
                formb.submitted_to_reviewers=True
                # Log admin action for FormB
                db_session.add(UserActivityLog(
                    user_id=session.get('id'),
                    action='assign_reviewers',
                    page='FORM B Ethics Assignment',
                    target_user_id=formb.user_id,
                    details=f"Assigned reviewers: {formb.reviewer_name1}, {formb.reviewer_name2} to FORM B for {formb.applicant_name}"
                ))
            else:
                    review_date_str = request.form.get('review_date')
                    if review_date_str:
                        try:
                            # Try parsing as DD/MM/YYYY
                            review_date_obj = datetime.strptime(review_date_str, "%d/%m/%Y")
                            formb.supervisor_date = review_date_obj
                        except ValueError:
                            try:
                                # Fallback: try parsing as YYYY-MM-DD
                                review_date_obj = datetime.strptime(review_date_str, "%Y-%m-%d")
                                formb.supervisor_date = review_date_obj
                            except ValueError:
                                formb.supervisor_date = None  # or handle error as needed
                    else:
                        formb.supervisor_date = None
                        formb.rejected_or_accepted = False
                        formb.submitted_to_reviewers = False
                        emails = []
                        emails.append(formb.email)
                        emails.append(formb.supervisor_email)
                    try:
                        message = f' Form belonging to {formb.applicant_name} was sent back. Please view feedback.'
                        send_email(app, mail, message, emails)
                    except Exception as e:
                        app.logger.error(f"Failed to send email")
            db_session.add(formb)
            db_session.commit()
            return redirect(url_for('chair_landing'))
        return render_template("form_b_ethics.html",formB=formb)
    elif form_name=="FORM C":
       
        formc = db_session.query(FormC).filter_by(form_id=id).first()
        
        Assigned_reviewer=''
        if formc:
            id_of_reviewers = get_reviewers_for_ethics_assignment(formc, FormC, FormC.submission_date)
            if id_of_reviewers:
                Assigned_reviewer = db_session.query(User).filter(User.user_id.in_(id_of_reviewers)).all()
 
        list_of_revewers=[]
        id_of_reviewers=[]
        if Assigned_reviewer:
            for item in Assigned_reviewer:
                id_of_reviewers.append(item.user_id)
                list_of_revewers.append(item.email)
            
        else:
            reviewers=request.form.getlist('reviewer_names[]')
            if len(reviewers) >= 2:
                Assigned_reviewer=db_session.query(User).filter(User.user_id.in_([reviewers[0], reviewers[1]])).all()
            
        if request.method=="POST":
            reviewers=request.form.getlist('reviewer_names[]')
            if request.form.get('accept') in ['Accept','Approved with Minor Changes'] and len(reviewers) > 2:
                flash('Please select no more than two reviewers before submitting.', 'danger')
                return redirect(url_for('ethics_reviewer_committee_forms', id=id, form_name=form_name))

            effective_reviewer_ids = resolve_reviewer_ids(reviewers, id_of_reviewers)
            if request.form.get('accept') in ['Accept','Approved with Minor Changes'] and len(effective_reviewer_ids) < 1:
                flash('Please assign at least one reviewer before submitting.', 'danger')
                return redirect(url_for('ethics_reviewer_committee_forms', id=id, form_name=form_name))

            _reviewers_emails=[]
            if reviewers:
                _reviewers_emails=db_session.query(User).filter(User.user_id.in_(effective_reviewer_ids)).all()

            formc.reviewer_name1 = effective_reviewer_ids[0] if len(effective_reviewer_ids) >= 1 else None
            formc.reviewer_name2 = effective_reviewer_ids[1] if len(effective_reviewer_ids) >= 2 else None
            formc.ethics_supervisor_signature_date=datetime.now()
            formc.review_form_comments=request.form.get('additional_comments')
            formc.ethics_supervisor_form_status=request.form.get('recommendation')
            
            if request.form.get('accept') in ['Accept','Approved with Minor Changes']:
                if Assigned_reviewer:
                    #Uncomment the code bellow for testing
                    ##
                    for item in Assigned_reviewer:
                        list_of_revewers.append(item.email)
                    
                    try:
                        message=f' You areassigned as a reviewer for a form belonging to {formc.applicant_name}. Please log into the ethics application system and review the form' 
            
                        send_email(app,mail, message,list_of_revewers)
                    except Exception as e:
                        print(f"Error sending email: {e}")

                else:
                    #Uncomment the code bellow for testing
                    ##
                    try:
                        message=f'You areassigned as a reviewer for a form belonging to {formc.applicant_name}. ,Please log into the ethic applications system and review the form' 
            
                        send_email(app,mail, message,list_of_revewers)
                    except Exception as e:
                        print(f"Error sending email: {e}")

                formc.rejected_or_accepted=True
                formc.submitted_to_reviewers=True
                # Log admin action for FormC
                db_session.add(UserActivityLog(
                    user_id=session.get('id'),
                    action='assign_reviewers',
                    page='FORM C Ethics Assignment',
                    target_user_id=formc.user_id,
                    details=f"Assigned reviewers: {formc.reviewer_name1}, {formc.reviewer_name2} to FORM C for {formc.applicant_name}"
                ))
            else:
                formc.supervisor_date=request.form.get('review_date')
                formc.rejected_or_accepted=False
                formc.submitted_to_reviewers=False
                emails=[]
                emails.append(formc.email_address)
                emails.append(formc.supervisor_email)
                try:
                    message=f' Form belonging to {formc.applicant_name} was sent back. Please view feedback.' 
            
                    send_email(app,mail, message,emails)
                except Exception as e:
                    app.logger.error(f"Failed to send email")
            db_session.add(formc)
            db_session.commit()
            return redirect(url_for('chair_landing'))
        return render_template("form_c_ethics.html",formc=formc)



@app.route('/request-reset', methods=['POST'])
def request_reset():
    email = request.form.get('email')
    token = generate_reset_token(email)
    if token:
        reset_link = url_for('reset_password', token=token, _external=True)
        send_email(
            to=email,
            subject="Password Reset",
            body=f"Click here to reset: {reset_link}"
        )
        return "Reset email sent!"
    return "Email not found", 404

from sqlalchemy.orm import aliased
@app.route('/supervisor_dashboard', methods=['GET','POST'])
def supervisor_dashboard():
    supervisor_id=session.get('id')
    
    role=session.get('supervisor_role')
    if not role:
        return redirect('/login?system=ethics')
    #supervisor_id="bea65156-03ff-45c8-bd41-9d07f4bc48d2"
    if not supervisor_id:
        return jsonify({'error': 'Unauthorized'}), 401
 
    # Global stats (limited to avoid performance issues) - these are for dashboard stats only
    formA = db_session.query(FormA).filter(FormA.submitted_at != None).order_by(FormA.submitted_at.desc()).limit(5).all()
    
    # Safe FormB query - only load needed columns to avoid binary column issues (LIMITED)
    formB_results = db_session.query(
        FormB.form_id, FormB.user_id, FormB.applicant_name, FormB.student_number,
        FormB.email, FormB.supervisor, FormB.supervisor_email, FormB.submitted_at,
        FormB.recommendation, FormB.supervisor_date, FormB.ethics_supervisor_form_status,
        FormB.signature_date, FormB.review_supervisor_signature, FormB.review_date,
        FormB.review_supervisor_signature1, FormB.review_date1, FormB.created_at, FormB.declaration_date
    ).filter(FormB.submitted_at != None).order_by(FormB.submitted_at.desc()).limit(5).all()
    
    # Convert tuples to proxy objects
    formB = []
    for result in formB_results:
        class FormBProxy:
            pass
        proxy = FormBProxy()
        proxy.form_id = result.form_id
        proxy.user_id = result.user_id
        proxy.applicant_name = result.applicant_name
        proxy.student_number = result.student_number
        proxy.email = result.email
        proxy.supervisor = result.supervisor
        proxy.supervisor_email = result.supervisor_email
        proxy.submitted_at = result.submitted_at
        proxy.recommendation = result.recommendation
        proxy.supervisor_date = result.supervisor_date
        proxy.ethics_supervisor_form_status = result.ethics_supervisor_form_status
        proxy.signature_date = result.signature_date
        proxy.review_supervisor_signature = result.review_supervisor_signature
        proxy.review_date = result.review_date
        proxy.review_supervisor_signature1 = result.review_supervisor_signature1
        proxy.review_date1 = result.review_date1
        proxy.created_at = result.created_at
        proxy.declaration_date = result.declaration_date
        formB.append(proxy)
    
    formC = db_session.query(FormC).filter(FormC.submission_date != None).order_by(FormC.submission_date.desc()).limit(5).all()
    
 
    # Query FormA and its FormARequirements for supervisor's users - SIMPLIFIED
    supervisor_formA_raw = (
        db_session.query(FormA, FormARequirements)
        .join(User, FormA.user_id == User.user_id)
        .outerjoin(FormARequirements, FormARequirements.user_id == FormA.user_id)
        .filter(User.supervisor_id == supervisor_id, FormA.submitted_at != None)
        .order_by(FormA.user_id, FormA.submitted_at.desc())
        .all()
    )
    
    # Keep only the latest per user and add count
    seen_users_a = set()
    supervisor_formA = []
    forma_counts = {}
    
    # First pass: count submissions per user
    for forma, req in supervisor_formA_raw:
        if forma.user_id not in forma_counts:
            forma_counts[forma.user_id] = 0
        forma_counts[forma.user_id] += 1
    
    # Second pass: keep latest per user
    for forma, req in supervisor_formA_raw:
        if forma.user_id not in seen_users_a:
            count = forma_counts.get(forma.user_id, 0)
            supervisor_formA.append((forma, req, count))
            seen_users_a.add(forma.user_id)
    
    # Query FormB and its FormARequirements for supervisor's users - SIMPLIFIED
    supervisor_formB_raw = (
        db_session.query(FormB, FormARequirements)
        .join(User, FormB.user_id == User.user_id)
        .outerjoin(FormARequirements, FormARequirements.user_id == FormB.user_id)
        .filter(User.supervisor_id == supervisor_id, FormB.submitted_at != None)
        .order_by(FormB.user_id, FormB.submitted_at.desc())
        .all()
    )
    
    # Keep only the latest per user and add count
    seen_users = set()
    supervisor_formB = []
    formb_counts = {}
    
    # First pass: count submissions per user
    for formb, req in supervisor_formB_raw:
        if formb.user_id not in formb_counts:
            formb_counts[formb.user_id] = 0
        formb_counts[formb.user_id] += 1
    
    # Second pass: keep latest per user
    for formb, req in supervisor_formB_raw:
        if formb.user_id not in seen_users:
            count = formb_counts.get(formb.user_id, 0)
            supervisor_formB.append((formb, req, count))
            seen_users.add(formb.user_id)
    
    # Subquery to count all FormC submissions per user and get latest - SIMPLIFIED
    supervisor_formC_raw = (
        db_session.query(FormC, FormARequirements)
        .join(User, FormC.user_id == User.user_id)
        .outerjoin(FormARequirements, FormARequirements.user_id == FormC.user_id)
        .filter(User.supervisor_id == supervisor_id, FormC.submission_date != None)
        .order_by(FormC.user_id, FormC.submission_date.desc())
        .all()
    )
    
    # Keep only the latest per user and add count
    seen_users_c = set()
    supervisor_formC = []
    formc_counts = {}
    
    # First pass: count submissions per user
    for formc, req in supervisor_formC_raw:
        if formc.user_id not in formc_counts:
            formc_counts[formc.user_id] = 0
        formc_counts[formc.user_id] += 1
    
    # Second pass: keep latest per user
    for formc, req in supervisor_formC_raw:
        if formc.user_id not in seen_users_c:
            count = formc_counts.get(formc.user_id, 0)
            supervisor_formC.append((formc, req, count))
            seen_users_c.add(formc.user_id)
    
    #supervisor_formA_req=db_session.query(model).filter(FormARequirements.user_id == FormA.user_id).all()
    
    return render_template("supervisor-dashboard.html",supervisor_role=role,formA=formA,formB=formB,formC=formC,supervisor_formA=supervisor_formA,supervisor_formB=supervisor_formB,supervisor_formC=supervisor_formC)



@app.route('/supervisor_dashboard_previous_forms/<string:user_id>', methods=['GET','POST'])
def supervisor_dashboard_previous_forms(user_id):
    supervisor_id=session.get('id')
    supervisor_role=session.get('supervisor_role')
    if not supervisor_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    formA = db_session.query(FormA).filter(FormA.user_id==user_id).all()
    
    # Safe FormB query - only load needed columns to avoid binary column issues
    formB_results = db_session.query(
        FormB.form_id, FormB.user_id, FormB.applicant_name, FormB.student_number,
        FormB.email, FormB.supervisor, FormB.supervisor_email, FormB.submitted_at,
        FormB.recommendation, FormB.supervisor_date, FormB.ethics_supervisor_form_status,
        FormB.signature_date, FormB.review_supervisor_signature, FormB.review_date,
        FormB.review_supervisor_signature1, FormB.review_date1, FormB.created_at, FormB.declaration_date,
        FormB.status, FormB.review_form_status, FormB.rejected_or_accepted
    ).filter(FormB.user_id==user_id).all()
    
    # Convert tuples to proxy objects
    formB = []
    for result in formB_results:
        class FormBProxy:
            pass
        proxy = FormBProxy()
        proxy.form_id = result.form_id
        proxy.user_id = result.user_id
        proxy.applicant_name = result.applicant_name
        proxy.student_number = result.student_number
        proxy.email = result.email
        proxy.supervisor = result.supervisor
        proxy.supervisor_email = result.supervisor_email
        proxy.submitted_at = result.submitted_at
        proxy.recommendation = result.recommendation
        proxy.supervisor_date = result.supervisor_date
        proxy.ethics_supervisor_form_status = result.ethics_supervisor_form_status
        proxy.signature_date = result.signature_date
        proxy.review_supervisor_signature = result.review_supervisor_signature
        proxy.review_date = result.review_date
        proxy.review_supervisor_signature1 = result.review_supervisor_signature1
        proxy.review_date1 = result.review_date1
        proxy.created_at = result.created_at
        proxy.declaration_date = result.declaration_date
        proxy.status = result.status
        proxy.review_form_status = result.review_form_status
        proxy.rejected_or_accepted = result.rejected_or_accepted
        formB.append(proxy)
    
    formC = db_session.query(FormC).filter(FormC.user_id==user_id).all()

    supervisor_formA = db_session.query(FormA, FormARequirements) \
        .join(User, FormA.user_id == User.user_id) \
        .outerjoin(FormARequirements, FormARequirements.user_id == FormA.user_id) \
        .filter(FormA.user_id==user_id) \
        .order_by(FormA.submitted_at.desc() ,FormA.declaration_date.desc()) \
        .all()
    
    # Safe FormB query with joins - only load needed columns to avoid binary column issues
    supervisor_formB_results = db_session.query(
        FormB.form_id, FormB.user_id, FormB.applicant_name, FormB.student_number,
        FormB.email, FormB.supervisor, FormB.supervisor_email, FormB.submitted_at,
        FormB.recommendation, FormB.supervisor_date, FormB.ethics_supervisor_form_status,
        FormB.signature_date, FormB.review_supervisor_signature, FormB.review_date,
        FormB.review_supervisor_signature1, FormB.review_date1, FormB.created_at, FormB.declaration_date,
        FormB.status, FormB.review_form_status, FormB.rejected_or_accepted,
        FormARequirements
    ).join(User, FormB.user_id == User.user_id) \
    .outerjoin(FormARequirements, FormARequirements.user_id == FormB.user_id) \
    .filter(FormB.user_id==user_id) \
    .order_by(FormB.submitted_at.desc(), FormB.declaration_date.desc()) \
    .all()
    
    # Convert to simplified format: (FormB-like proxy, FormARequirements)
    supervisor_formB = []
    for result in supervisor_formB_results:
        class FormBProxy:
            pass
        proxy = FormBProxy()
        proxy.form_id = result.form_id
        proxy.user_id = result.user_id
        proxy.applicant_name = result.applicant_name
        proxy.student_number = result.student_number
        proxy.email = result.email
        proxy.supervisor = result.supervisor
        proxy.supervisor_email = result.supervisor_email
        proxy.submitted_at = result.submitted_at
        proxy.recommendation = result.recommendation
        proxy.supervisor_date = result.supervisor_date
        proxy.ethics_supervisor_form_status = result.ethics_supervisor_form_status
        proxy.signature_date = result.signature_date
        proxy.review_supervisor_signature = result.review_supervisor_signature
        proxy.review_date = result.review_date
        proxy.review_supervisor_signature1 = result.review_supervisor_signature1
        proxy.review_date1 = result.review_date1
        proxy.created_at = result.created_at
        proxy.declaration_date = result.declaration_date
        proxy.status = result.status
        proxy.review_form_status = result.review_form_status
        proxy.rejected_or_accepted = result.rejected_or_accepted
        supervisor_formB.append((proxy, result.FormARequirements))
    
    supervisor_formC = db_session.query(FormC, FormARequirements) \
        .join(User, FormC.user_id == User.user_id) \
        .outerjoin(FormARequirements, FormARequirements.user_id == FormC.user_id) \
        .filter(FormC.user_id==user_id) \
        .order_by(FormC.submission_date.desc()) \
        .all()
    
    return render_template("supervisor_form_version_control.html",supervisor_role=supervisor_role,formA=formA,formB=formB,formC=formC,supervisor_formA=supervisor_formA,supervisor_formB=supervisor_formB,supervisor_formC=supervisor_formC)



@app.route('/dean_dashboard', methods=['GET','POST'])
def dean_dashboard():
    role="STUDENT"
    supervisor_formA = db_session.query(FormA).join(User, FormA.user_id == User.user_id).all()
    
    # Safe FormB query - only load needed columns to avoid binary column issues
    supervisor_formB_results = db_session.query(
        FormB.form_id, FormB.user_id, FormB.applicant_name, FormB.student_number,
        FormB.email, FormB.supervisor, FormB.supervisor_email, FormB.submitted_at,
        FormB.recommendation, FormB.supervisor_date, FormB.ethics_supervisor_form_status,
        FormB.signature_date, FormB.review_supervisor_signature, FormB.review_date,
        FormB.review_supervisor_signature1, FormB.review_date1, FormB.created_at, FormB.declaration_date
    ).join(User, FormB.user_id == User.user_id).all()
    
    # Convert tuples to proxy objects
    supervisor_formB = []
    for result in supervisor_formB_results:
        class FormBProxy:
            pass
        proxy = FormBProxy()
        proxy.form_id = result.form_id
        proxy.user_id = result.user_id
        proxy.applicant_name = result.applicant_name
        proxy.student_number = result.student_number
        proxy.email = result.email
        proxy.supervisor = result.supervisor
        proxy.supervisor_email = result.supervisor_email
        proxy.submitted_at = result.submitted_at
        proxy.recommendation = result.recommendation
        proxy.supervisor_date = result.supervisor_date
        proxy.ethics_supervisor_form_status = result.ethics_supervisor_form_status
        proxy.signature_date = result.signature_date
        proxy.review_supervisor_signature = result.review_supervisor_signature
        proxy.review_date = result.review_date
        proxy.review_supervisor_signature1 = result.review_supervisor_signature1
        proxy.review_date1 = result.review_date1
        proxy.created_at = result.created_at
        proxy.declaration_date = result.declaration_date
        supervisor_formB.append(proxy)
    
    supervisor_formC = db_session.query(FormC).join(User, FormC.user_id == User.user_id).all()
    supervisor_formA_req=db_session.query(FormARequirements).filter(FormARequirements.user_id == User.user_id).all()
    students=db_session.query(User).filter(User.role==role).all()
    
    return render_template('dean.html',students=students,supervisor_formA_req=supervisor_formA_req,supervisor_formA=supervisor_formA,supervisor_formB=supervisor_formB,supervisor_formC=supervisor_formC)



@app.route('/supervisor_student', methods=['GET', 'POST'])
def supervisor_student ():
    supervisor_id=session.get('id')
    supervisor_data = (
    db_session.query(User)
    .options(
        joinedload(User.form_a),
        joinedload(User.form_b),
        joinedload(User.form_c),
        joinedload(User.form_a_requirements)
    )
    .filter(User.role == "STUDENT", User.supervisor_id == supervisor_id)
    .all()
        )


    return render_template('students.html',students=supervisor_data)

def validate_reset_token(token):
    user = User.query.filter_by(reset_token=token).first()
    if user and user.reset_token_expiry > datetime.utcnow():
        return user  # Token is valid
    return None  # Token is invalid/expired


# =====================================================================================================
# FILE DOWNLOAD ROUTES - PRODUCTION FIX
# =====================================================================================================

@app.route('/uploads/<path:filename>')
def download_file(filename):
    """
    Serve uploaded files with security checks.
    CRITICAL FIX: This route was missing, causing 404 errors for all uploaded attachments.
    """
    try:
        # Security: Only serve files from the uploads directory
        safe_path = secure_filename(filename)
        if not safe_path or safe_path != filename:
            flash("Invalid file path", "danger")
            return redirect(url_for('dashboard'))
        
        # Check if user is logged in
        if 'id' not in session:
            flash("You must be logged in to access files", "warning")
            return redirect(url_for('login'))
        
        # PRODUCTION FIX: Use the same upload directory logic as file saving
        upload_dir = get_upload_folder()
        
        # Try direct filename first
        file_path = os.path.join(upload_dir, safe_path)
        if not os.path.exists(file_path):
            # Try removing the uploads/form prefix if it exists in the filename
            if safe_path.startswith('uploads/form/'):
                clean_filename = safe_path.replace('uploads/form/', '')
                file_path = os.path.join(upload_dir, clean_filename)
            elif safe_path.startswith('form/'):
                clean_filename = safe_path.replace('form/', '')
                file_path = os.path.join(upload_dir, clean_filename)
        
        if not os.path.exists(file_path):
            print(f"âš ï¸ File not found: {file_path}")
            flash("File not found. It may have been deleted during deployment.", "danger")
            return redirect(url_for('dashboard'))
            
        # TODO: Add additional security - check if user has permission to access this specific file
        # This would require storing file ownership in database
        
        return send_from_directory(
            upload_dir,
            os.path.basename(file_path),
            as_attachment=True
        )
        
    except Exception as e:
        print(f"âš ï¸ File download error: {str(e)}")
        flash("Error accessing file", "danger")
        return redirect(url_for('dashboard'))


# =====================================================================================================
# EMAIL REMINDER SYSTEM
# =====================================================================================================

def get_students_with_missing_documents():
    """
    Get students who have submitted forms but have missing documents
    Returns list of (user, missing_files_info) tuples
    """
    students_with_missing_files = []
    
    # Get all users with FormARequirements (students who submitted forms)
    form_requirements = db_session.query(FormARequirements).join(User).all()
    
    for req in form_requirements:
        user = db_session.query(User).filter_by(user_id=req.user_id).first()
        if not user:
            continue
            
        # Check if files exist on filesystem
        upload_folder = get_upload_folder()
        missing_files = {}
        
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
            file_data = getattr(req, field_name)
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
                        missing_files[field_name] = display_name
        
        # Only add students who have missing files
        if missing_files:
            students_with_missing_files.append((user, missing_files))
    
    return students_with_missing_files

@app.route('/send_missing_documents_reminder', methods=['POST'])
def send_missing_documents_reminder():
    """
    Admin route to send email reminders to students with missing documents
    Only sends to students who have submitted forms but are missing files
    """
    try:
        # Check if user is logged in
        user_id = session.get('id')
        if not user_id:
            flash("Please log in to access this feature.", "warning")
            return redirect(url_for('login'))
        
        # Check if user is admin (you can modify this condition based on your admin check)
        user_role = session.get('role')
        if user_role not in ['admin', 'chair', 'dean']:  # Adjust roles as needed
            flash("Unauthorized access. Admin privileges required.", "danger")
            return redirect(url_for('dashboard'))
        
        students_with_missing_files = get_students_with_missing_documents()
        
        if not students_with_missing_files:
            flash("No students with missing documents found.", "info")
            return redirect(request.referrer or url_for('dashboard'))
        
        emails_sent = 0
        failed_emails = 0
        
        for user, missing_files in students_with_missing_files:
            try:
                # Create email message
                missing_files_list = ', '.join(missing_files.values())
                
                message_body = f"""
Dear {user.full_name},

We hope this email finds you well.

Our system has detected that some of your uploaded documents for your ethics application are currently missing from our servers. This may have occurred due to recent system maintenance.

To ensure your application can be processed without delays, please re-upload the missing documents by:

1. Logging into your student dashboard
2. Clicking on the "Reupload Documents" button if you see the missing files alert
3. Selecting your form type and uploading the required documents

If you experience any difficulties or have questions, please don't hesitate to contact our ethics committee.

Thank you for your attention to this matter.

Best regards,
Ethics Committee
"""

                # Send email using existing email function
                send_email(
                    app=current_app,
                    mail=mail,
                    message=message_body,
                    recipient=[user.email]
                )
                
                emails_sent += 1
                print(f"âœ… Reminder email sent to {user.email}")
                
            except Exception as e:
                failed_emails += 1
                print(f"âš ï¸ Failed to send email to {user.email}: {str(e)}")
                continue
        
        # Flash success/failure message
        if emails_sent > 0:
            flash(f"Successfully sent reminder emails to {emails_sent} student(s).", "success")
        if failed_emails > 0:
            flash(f"Failed to send {failed_emails} email(s). Please check email configuration.", "warning")
            
        return redirect(request.referrer or url_for('dashboard'))
        
    except Exception as e:
        print(f"âš ï¸ Error sending reminder emails: {str(e)}")
        flash("Error sending reminder emails. Please try again later.", "danger")
        return redirect(request.referrer or url_for('dashboard'))

@app.route('/api/missing_documents_count', methods=['GET'])
def get_missing_documents_count():
    """
    API endpoint to get count of students with missing documents
    """
    try:
        # Check if user is logged in
        user_id = session.get('id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Check if user is admin
        user_role = session.get('role')
        if user_role not in ['admin', 'chair', 'dean']:
            return jsonify({'error': 'Admin privileges required'}), 403
        
        students_with_missing_files = get_students_with_missing_documents()
        
        return jsonify({
            'count': len(students_with_missing_files),
            'students': [
                {
                    'name': user.full_name,
                    'email': user.email,
                    'missing_files': list(missing_files.values())
                } 
                for user, missing_files in students_with_missing_files
            ]
        })
        
    except Exception as e:
        print(f"âš ï¸ Error getting missing documents count: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# =====================================================================================================
# END OF FORMS
# =====================================================================================================


UPLOAD_FOLDER = "/opt/render/project/src/static/uploads/form"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/upload_to", methods=["POST"])
def upload_to():
    file = request.files["file"]
    file.save(os.path.join(UPLOAD_FOLDER, file.filename))
    return "File uploaded!"



