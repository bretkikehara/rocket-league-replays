from datetime import timedelta

from cms.apps.media.models import ImageRefField
from cms.apps.pages.models import ContentBase, Page
from cms.models import HtmlField
from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import now


class Content(ContentBase):

    class Meta:
        verbose_name = 'homepage'


class ContentColumn(models.Model):
    page = models.ForeignKey(Page)

    title = models.CharField(
        max_length=100,
    )

    url = models.CharField(
        "URL",
        max_length=100,
    )

    image = ImageRefField()


class Placeholder(ContentBase):
    pass


class StandardPage(ContentBase):

    content_primary = HtmlField(
        blank=True,
        null=True,
    )


class Patron(models.Model):

    # Pledge details
    pledge_id = models.PositiveIntegerField(
        b"Pledge ID",
    )

    pledge_amount = models.PositiveIntegerField(
        help_text=b"Amount pledged (in cents)"
    )

    pledge_created = models.DateTimeField()

    pledge_declined_since = models.DateTimeField(
        null=True,
        blank=True,
    )

    # Patron details
    patron_id = models.PositiveIntegerField(
        b"Patron ID",
    )

    patron_email = models.EmailField()

    def __str__(self):
        return self.patron_email


class PatronTrial(models.Model):

    user = models.ForeignKey(User)

    expiry_date = models.DateField(
        default=now() + timedelta(days=7)
    )

    def __str__(self):
        return str(self.user)
