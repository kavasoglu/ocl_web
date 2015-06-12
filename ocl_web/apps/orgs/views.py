import requests

from django.shortcuts import redirect
from django.http import Http404
from django.views.generic import TemplateView, View
from django.views.generic.edit import FormView
from django.core.urlresolvers import reverse
from django.contrib import messages
from django.utils.translation import ugettext as _
from django.core.paginator import Paginator
from braces.views import LoginRequiredMixin
from braces.views import (CsrfExemptMixin, JsonRequestResponseMixin)

from .forms import (OrganizationCreateForm, OrganizationEditForm)
from .forms import (OrganizationMemberAddForm)
from libs.ocl import OCLapi, OCLSearch


class OrganizationDetailView(TemplateView):
    """
        Organization details and source search view.
    """

    template_name = "orgs/org_detail.html"

    def get_context_data(self, *args, **kwargs):
        """Gets the org first, then the sources of that org, and then the
        concepts from each of those sources.

        Final context
        -------------
        context['org']
        context['sources']
        context['collections']
        context['members']
        """

        context = super(OrganizationDetailView, self).get_context_data(*args, **kwargs)

        org_id = self.kwargs.get('org')
        res_type = self.request.GET.get('resource_type')
        print 'INPUT PARAMS %s: %s' % (self.request.method, self.request.GET)
        print res_type
        if res_type == 'source':
            source_searcher = OCLSearch(OCLapi.SOURCE_TYPE).parse(self.request.GET)
            collection_searcher = OCLSearch(OCLapi.COLLECTION_TYPE).parse(None)
        elif res_type == 'collection':
            source_searcher = OCLSearch(OCLapi.SOURCE_TYPE).parse(None)
            collection_searcher = OCLSearch(OCLapi.COLLECTION_TYPE).parse(self.request.GET)
        else:
            # need to pass down paging parameters
            source_searcher = OCLSearch(OCLapi.SOURCE_TYPE).parse(self.request.GET)
            collection_searcher = OCLSearch(OCLapi.COLLECTION_TYPE).parse(self.request.GET)

        api = OCLapi(self.request, debug=True)

        results = api.get('orgs', org_id)
        if results.status_code != 200:
            if results.status_code == 404:
                raise Http404
            else:
                results.raise_for_status()
        org = results.json()
        if org.extras:
            org.extras = json.loads(org.extras)

        results = api.get('orgs', org_id, 'sources', params=source_searcher.search_params)
        if results.status_code == requests.codes.not_found:
            num_found = 0
            sources = []
            context['source_page'] = None
        else:
            num_found = int(results.headers['num_found'])
            sources = results.json()
            pg = Paginator(range(num_found), source_searcher.num_per_page)
            context['source_page'] = pg.page(source_searcher.current_page)

        context['source_pagination_url'] = self.request.get_full_path()
        context['sources'] = sources
        context['source_filters'] = source_searcher.get_filters()
        context['search_sort_options'] = source_searcher.get_sort_options()
        context['search_sort'] = source_searcher.get_sort()
        context['source_q'] = source_searcher.get_query()

        results = api.get('orgs', org_id, 'collections', params=collection_searcher.search_params)
        if results.status_code == requests.codes.not_found:
            collections = []
            num_found = 0
            context['collection_page'] = None
        else:
            collections = results.json()
            num_found = int(results.headers['num_found'])
            pg = Paginator(range(num_found), collection_searcher.num_per_page)
            context['collection_page'] = pg.page(collection_searcher.current_page)

        context['collection_pagination_url'] = self.request.get_full_path()
        context['collections'] = collections
        context['collection_filters'] = collection_searcher.get_filters()

        # TODO: access issue, error if user is not super user??
        members = []
        r = api.get('orgs', org_id, 'members')
        if r.status_code == 200:
            members = r.json()
        elif r.status_code != 404:
#            raise Exception(r.json())
            pass
        # Set the context

        context['org'] = org
        context['members'] = members
        return context


class OrganizationCreateView(LoginRequiredMixin, FormView):

    form_class = OrganizationCreateForm
    template_name = "orgs/org_new.html"

    def form_valid(self, form, *args, **kwargs):

        org_id = form.cleaned_data.pop('short_name')

        api = OCLapi(self.request, debug=True)

        data = {
            'id': org_id,
        }
        data.update(form.cleaned_data)
        print form.cleaned_data
        print data
        result = api.create_org(data)

        # TODO:  Catch exceptions that will be raised by
        # Ocl lib.
        if result.ok:
            messages.add_message(self.request, messages.INFO, _('Organization Added'))
            return redirect(reverse('org-detail', kwargs={'org': org_id}))

        # TODO:  Add error messages from API to form.
        else:
            return super(OrganizationCreateView, self).form_invalid(self, *args, **kwargs)


class OrganizationEditView(FormView):

    template_name = 'orgs/org_edit.html'

    def get_form_class(self):
        """ Trick to do some initial lookup """
        self.org_id = self.kwargs.get('org')
        api = OCLapi(self.request, debug=True)
        self.org = api.get('orgs', self.org_id).json()
        return OrganizationEditForm

    def get_context_data(self, *args, **kwargs):

        context = super(OrganizationEditView, self).get_context_data(*args, **kwargs)
        context['org'] = self.org
        return context

    def get_initial(self):
        return self.org

    def form_valid(self, form, *args, **kwargs):

        api = OCLapi(self.request, debug=True)

        data = {}
        data.update(form.cleaned_data)
        result = api.update_org(self.org_id, data)
        # TODO:  Catch exceptions that will be raised by
        # Ocl lib.
        if result.ok:
            messages.add_message(self.request, messages.INFO, _('Organization updated.'))
            return redirect(reverse('org-detail', kwargs={'org': self.org_id}))

        # TODO:  Add error messages from API to form.
        else:
            return super(OrganizationEditView, self).form_invalid(form)


class OrganizationMemberAddView(LoginRequiredMixin, FormView):

    form_class = OrganizationMemberAddForm
    template_name = "orgs/org_member_add.html"

    def get_org(self):
        self.org_id = self.kwargs.get('org')
        api = OCLapi(self.request, debug=True)
        self.org = api.get('orgs', self.org_id).json()

    def get_initial(self):
        """ Trick to do some initial lookup """
        self.get_org()
        data = super(OrganizationMemberAddView, self).get_initial()
        return data

    def get_context_data(self, *args, **kwargs):
        """
        """
        context = super(OrganizationMemberAddView, self).get_context_data(*args, **kwargs)
        context['org'] = self.org
        return context

    def form_valid(self, form, *args, **kwargs):
        print args
        print kwargs
        self.get_org()
        new_username = form.cleaned_data.pop('member_username')

        api = OCLapi(self.request, debug=True)

        result = api.put('orgs', self.org['id'], 'members', new_username)

        # TODO:  Catch exceptions that will be raised by
        # Ocl lib.
        if result.status_code == 204:
            messages.add_message(self.request, messages.INFO, _('Member Added'))
            return redirect(reverse('org-detail', kwargs={'org': self.org['id']}))

        # TODO:  Add error messages from API to form.
        else:
            return super(OrganizationMemberAddView, self).form_invalid(form)


class OrganizationMemberRemoveView(LoginRequiredMixin,
                                   JsonRequestResponseMixin, View):

    def post(self, *args, **kwargs):
        self.org_id = self.kwargs.get('org')
        self.username = self.kwargs.get('username')

        api = OCLapi(self.request, debug=True)
        result = api.delete('orgs', self.org_id, 'members', self.username)

        return self.render_json_response({'message':'Member removed'})
        if result.status_code == 204:
            return self.render_json_response({'message':'Member removed'})

        else:
            return self.render_bad_request_response({'message': result.status_code})


