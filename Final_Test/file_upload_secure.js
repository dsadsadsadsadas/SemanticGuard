const fileFilter = (req, file, cb) => {
    if (file.mimetype === 'image/jpeg' || file.mimetype === 'image/png') cb(null, true);
    else cb(new Error('Invalid file type'), false);
};
// SAFE: Strict File Upload filter
const upload = multer({ dest: 'uploads/', fileFilter });
app.post('/profile_pic', upload.single('avatar'), function (req, res) {
    res.send('File uploaded!');
});
