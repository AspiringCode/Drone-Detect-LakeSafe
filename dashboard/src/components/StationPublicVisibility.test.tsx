import {fireEvent,render,screen} from '@testing-library/react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {StationPublicVisibility} from './StationPublicVisibility';
import {apiRequest} from '../lib/apiClient';
vi.mock('../lib/apiClient',()=>({apiRequest:vi.fn()}));
const request=vi.mocked(apiRequest);
describe('Station public pages',()=>{
  beforeEach(()=>request.mockReset());
  it('confirms the affected public content and saves the selected station only',async()=>{
    request.mockResolvedValueOnce({visible:true,published_lakes:1,lakes:[{lake_id:'lake-a',name:'Lake A'}]})
      .mockResolvedValueOnce({visible:false,published_lakes:1});
    render(<StationPublicVisibility stationId="a"/>);
    fireEvent.click(await screen.findByRole('button',{name:'Close public lake pages'}));
    expect(screen.getByRole('dialog')).toHaveTextContent('Hide this station’s lakes');
    fireEvent.click(screen.getByRole('button',{name:'Close pages'}));
    expect(await screen.findByText(/Closed to public viewers/)).toBeVisible();
    expect(request).toHaveBeenLastCalledWith('/api/stations/a/public-visibility',expect.objectContaining({body:'{"visible":false}'}),expect.anything());
  });
  it('does not claim success when the visibility write fails',async()=>{
    request.mockResolvedValueOnce({visible:false,lakes:[]}).mockRejectedValueOnce(new Error('Save unavailable'));
    render(<StationPublicVisibility stationId="a"/>);
    fireEvent.click(await screen.findByRole('button',{name:'Open public lake pages'}));
    fireEvent.click(screen.getByRole('button',{name:'Open pages'}));
    expect(await screen.findByText('Save unavailable')).toBeVisible();
    expect(screen.queryByText(/Open to public viewers/)).toBeNull();
  });
});
