"""Package preset layout.

Package ini memasang preset layout bawaan. Setiap modul preset mengekspos
``LAYOUT: LayoutSpec``; registry menemukan dan mengurutkannya secara
deterministik berdasarkan ``layout_id``.

Preset konten dan chart memakai ``vertical_align="center"`` agar row konten
tidak menumpuk di atas. Chart 16:9 tidak memenuhi seluruh tinggi area konten,
sehingga row chart juga memakai aturan centering yang sama.
"""
