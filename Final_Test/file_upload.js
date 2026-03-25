const upload = multer({ dest: 'uploads/' });
app.post('/profile_pic', upload.single('avatar'), function (req, res) {
    // VULNERABLE: Unrestricted File Upload (No validation on mimetype or extension)
    res.send('File uploaded!');
});
